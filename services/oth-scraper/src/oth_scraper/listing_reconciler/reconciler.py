"""Reconcile a batch of OTH listings into the Property/Listing/Snapshot tables."""
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oth_scraper.db.models import Listing, ListingSnapshot, Property
from oth_scraper.oth_client.types import Category, OTHListing
from oth_scraper.snapshot_diff import ChangedFields, diff

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconcileResult:
    """Counts emitted by `reconcile_batch` for one job's batch."""

    properties_upserted: int
    listings_opened: int
    snapshots_written: int
    observations_unchanged: int


async def reconcile_batch(
    suburb_id: int,
    category: Category,
    listings: list[OTHListing],
    raw_payloads: list[dict],
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> ReconcileResult:
    """Reconcile one (suburb, category) page of OTH search results.

    Each OTHListing maps to one transactional unit so a bad row doesn't
    poison the rest of the batch. Tests assert externally observable state
    after this returns; we don't expose intermediate handles.

    Args:
        suburb_id: PK of the suburb the job is scraping.
        category: Search category — one of the Category enum values.
        listings: Parsed OTH rows (issue 05's `OTHListing`).
        raw_payloads: Parallel list of raw OTH JSON dicts; `raw_payloads[i]`
            is the source for `listings[i]`. Stored verbatim on snapshots.
        session_factory: Async session factory bound to the live engine.

    Returns:
        Aggregate counts: properties_upserted, listings_opened,
        snapshots_written, observations_unchanged.
    """
    if len(listings) != len(raw_payloads):
        raise ValueError(
            f"listings ({len(listings)}) and raw_payloads "
            f"({len(raw_payloads)}) must be the same length"
        )

    properties_upserted = 0
    listings_opened = 0
    snapshots_written = 0
    observations_unchanged = 0

    for listing, raw in zip(listings, raw_payloads):
        async with session_factory() as session:
            async with session.begin():
                prop, prop_inserted = await _upsert_property(
                    session, listing, suburb_id
                )
                if prop_inserted:
                    properties_upserted += 1

                listing_row, listing_opened = await _find_or_open_listing(
                    session, prop.id, suburb_id, category, listing
                )
                if listing_opened:
                    listings_opened += 1

                latest = await _latest_snapshot(session, listing_row.id)
                changes = diff(latest, _ObservationView(listing))

                if changes is None:
                    observations_unchanged += 1
                else:
                    await _insert_snapshot(
                        session, listing_row.id, listing, raw, changes
                    )
                    snapshots_written += 1

                # Always: bump last_seen_at and reconcile agent/agency.
                await _touch_listing(session, listing_row, listing)

    logger.info(
        "reconcile_batch suburb=%s category=%s in=%d "
        "properties_upserted=%d listings_opened=%d "
        "snapshots_written=%d observations_unchanged=%d",
        suburb_id,
        category.value,
        len(listings),
        properties_upserted,
        listings_opened,
        snapshots_written,
        observations_unchanged,
    )
    return ReconcileResult(
        properties_upserted=properties_upserted,
        listings_opened=listings_opened,
        snapshots_written=snapshots_written,
        observations_unchanged=observations_unchanged,
    )


# --- helpers ---------------------------------------------------------------


class _ObservationView:
    """Wraps an OTHListing so it satisfies the snapshot_diff.SnapshotLike Protocol.

    The Protocol fields (price, title, blurb, bedrooms, bathrooms, parking,
    land_size_sqm, property_type, status) are read directly from the
    OTHListing — except `blurb`, which OTH's search API does not populate
    in v1 (issue 27 in the PRD). We surface it as `None`.
    """

    __slots__ = ("_l",)

    def __init__(self, listing: OTHListing) -> None:
        self._l = listing

    @property
    def price(self) -> int | None:
        return self._l.price

    @property
    def title(self) -> str | None:
        return self._l.title

    @property
    def blurb(self) -> str | None:
        return None

    @property
    def bedrooms(self) -> int | None:
        return self._l.bedrooms

    @property
    def bathrooms(self) -> int | None:
        return self._l.bathrooms

    @property
    def parking(self) -> int | None:
        return self._l.parking

    @property
    def land_size_sqm(self) -> int | None:
        # Snapshot column is Integer; OTH returns a float. Round defensively.
        if self._l.land_size_sqm is None:
            return None
        return int(round(self._l.land_size_sqm))

    @property
    def property_type(self) -> str | None:
        return self._l.property_type

    @property
    def status(self) -> str | None:
        return self._l.status


async def _upsert_property(
    session: AsyncSession,
    listing: OTHListing,
    suburb_id: int,
) -> tuple[Property, bool]:
    """Find or insert a Property row.

    Lookup order:
    1. By `oth_property_id` (the OTH-issued ID).
    2. Fallback by `(formatted_address, postcode)` — guards against OTH
       reissuing a propertyId for the same physical address.

    Returns the row and whether it was newly inserted.
    """
    if listing.oth_property_id:
        existing = await session.scalar(
            select(Property).where(
                Property.oth_property_id == listing.oth_property_id
            )
        )
        if existing is not None:
            _maybe_backfill_location(existing, listing)
            return existing, False

    existing = await session.scalar(
        select(Property).where(
            Property.formatted_address == listing.formatted_address,
            Property.postcode == listing.postcode,
        )
    )
    if existing is not None:
        # Backfill the OTH ID if we earlier inserted via the address fallback.
        if existing.oth_property_id is None and listing.oth_property_id:
            existing.oth_property_id = listing.oth_property_id
        _maybe_backfill_location(existing, listing)
        return existing, False

    prop = Property(
        oth_property_id=listing.oth_property_id,
        formatted_address=listing.formatted_address,
        postcode=listing.postcode,
        suburb_id=suburb_id,
        location=_make_point(listing.latitude, listing.longitude),
    )
    session.add(prop)
    await session.flush()
    return prop, True


def _make_point(lat: float | None, lon: float | None) -> str | None:
    """Build the `geography(Point, 4326)` value as WKT, or None if either is missing."""
    if lat is None or lon is None:
        return None
    return f"SRID=4326;POINT({lon} {lat})"


def _maybe_backfill_location(prop: Property, listing: OTHListing) -> None:
    """If the existing Property has no location but this listing supplies one, backfill."""
    if prop.location is None:
        point = _make_point(listing.latitude, listing.longitude)
        if point is not None:
            prop.location = point


async def _find_or_open_listing(
    session: AsyncSession,
    property_id: int,
    suburb_id: int,
    category: Category,
    listing: OTHListing,
) -> tuple[Listing, bool]:
    """Find the open Listing for (property, suburb, category), or open a new one.

    "Open" means `closed_at IS NULL`. A re-listing of the same property
    after a previous Listing has closed correctly produces a second row.
    """
    existing = await session.scalar(
        select(Listing).where(
            Listing.property_id == property_id,
            Listing.suburb_id == suburb_id,
            Listing.category == category.value,
            Listing.closed_at.is_(None),
        )
    )
    if existing is not None:
        return existing, False

    row = Listing(
        property_id=property_id,
        suburb_id=suburb_id,
        category=category.value,
        oth_listing_id=_extract_listing_id(listing),
        agent_name=listing.agent_name,
        agency_name=listing.agency_name,
    )
    session.add(row)
    await session.flush()
    return row, True


def _extract_listing_id(listing: OTHListing) -> str | None:
    """OTH's per-campaign ID is not on OTHListing today; the URL is the closest proxy.

    Returning `listing_url` keeps the column populated when present so future
    enrichment passes can dedupe campaigns; once issue 05 surfaces a real
    `oth_listing_id` field this becomes a one-line swap.
    """
    return listing.listing_url


async def _latest_snapshot(
    session: AsyncSession, listing_id: int
) -> ListingSnapshot | None:
    return await session.scalar(
        select(ListingSnapshot)
        .where(ListingSnapshot.listing_id == listing_id)
        .order_by(ListingSnapshot.observed_at.desc(), ListingSnapshot.id.desc())
        .limit(1)
    )


async def _insert_snapshot(
    session: AsyncSession,
    listing_id: int,
    listing: OTHListing,
    raw_payload: dict,
    changes: ChangedFields,
) -> None:
    view = _ObservationView(listing)
    snapshot = ListingSnapshot(
        listing_id=listing_id,
        price=view.price,
        title=view.title,
        blurb=view.blurb,
        bedrooms=view.bedrooms,
        bathrooms=view.bathrooms,
        parking=view.parking,
        land_size_sqm=view.land_size_sqm,
        property_type=view.property_type,
        status=view.status,
        raw_payload=raw_payload,
        changed_fields=list(changes.fields),
    )
    session.add(snapshot)
    await session.flush()


async def _touch_listing(
    session: AsyncSession, listing_row: Listing, observation: OTHListing
) -> None:
    """Bump last_seen_at; update agent/agency if they changed.

    No snapshot row is written for agent/agency changes — they live on the
    Listing, not the snapshot history (PRD: snapshot tracks signal not
    heartbeats; agent moves are not material to property analytics).
    """
    from sqlalchemy import func as sa_func

    listing_row.last_seen_at = sa_func.now()
    if observation.agent_name != listing_row.agent_name:
        listing_row.agent_name = observation.agent_name
    if observation.agency_name != listing_row.agency_name:
        listing_row.agency_name = observation.agency_name
