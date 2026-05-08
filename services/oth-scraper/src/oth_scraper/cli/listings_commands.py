"""CLI implementation for `oth listings ...` commands.

Mirrors the REST surface in ``api/routers/listings.py``.
"""
import typer
from sqlalchemy import select

from oth_scraper.db.engine import AsyncSessionLocal
from oth_scraper.db.models.listing import LISTING_CATEGORY_VALUES, Listing
from oth_scraper.db.models.listing_snapshot import ListingSnapshot


async def listings_ls_impl(
    *,
    suburb_id: int | None,
    category: str | None,
    active: bool,
    limit: int,
) -> None:
    if category is not None and category not in LISTING_CATEGORY_VALUES:
        typer.echo(
            f"--category must be one of {list(LISTING_CATEGORY_VALUES)}",
            err=True,
        )
        raise typer.Exit(code=2)

    async with AsyncSessionLocal() as session:
        stmt = select(Listing).order_by(Listing.id.desc())
        if suburb_id is not None:
            stmt = stmt.where(Listing.suburb_id == suburb_id)
        if category is not None:
            stmt = stmt.where(Listing.category == category)
        if active:
            stmt = stmt.where(Listing.closed_at.is_(None))
        stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        typer.echo("(no listings)")
        return
    for r in rows:
        closed = (
            f" closed={r.closed_at.isoformat()} reason={r.closure_reason}"
            if r.closed_at
            else ""
        )
        typer.echo(
            f"#{r.id:>6}  {r.category:<13}  property={r.property_id} "
            f"suburb={r.suburb_id}  last_seen={r.last_seen_at.isoformat()}"
            f"{closed}"
        )


async def listings_show_impl(*, listing_id: int) -> None:
    async with AsyncSessionLocal() as session:
        row = await session.get(Listing, listing_id)
        if row is None:
            typer.echo(f"Not found: listing {listing_id}", err=True)
            raise typer.Exit(code=1)
        latest = (
            await session.execute(
                select(ListingSnapshot)
                .where(ListingSnapshot.listing_id == listing_id)
                .order_by(
                    ListingSnapshot.observed_at.desc(),
                    ListingSnapshot.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    typer.echo(f"#{row.id} {row.category}")
    typer.echo(f"  property_id: {row.property_id}")
    typer.echo(f"  suburb_id: {row.suburb_id}")
    typer.echo(f"  oth_listing_id: {row.oth_listing_id}")
    typer.echo(f"  agent: {row.agent_name}  agency: {row.agency_name}")
    typer.echo(f"  first_seen_at: {row.first_seen_at.isoformat()}")
    typer.echo(f"  last_seen_at: {row.last_seen_at.isoformat()}")
    if row.closed_at:
        typer.echo(
            f"  closed_at: {row.closed_at.isoformat()} ({row.closure_reason})"
        )
    if latest is not None:
        typer.echo("  latest snapshot:")
        typer.echo(f"    observed_at: {latest.observed_at.isoformat()}")
        typer.echo(f"    price: {latest.price}")
        typer.echo(f"    bedrooms: {latest.bedrooms}")
        typer.echo(f"    status: {latest.status}")
        typer.echo(f"    changed_fields: {latest.changed_fields}")


async def listings_history_impl(*, listing_id: int) -> None:
    async with AsyncSessionLocal() as session:
        listing = await session.get(Listing, listing_id)
        if listing is None:
            typer.echo(f"Not found: listing {listing_id}", err=True)
            raise typer.Exit(code=1)
        rows = (
            await session.execute(
                select(ListingSnapshot)
                .where(ListingSnapshot.listing_id == listing_id)
                .order_by(
                    ListingSnapshot.observed_at.asc(), ListingSnapshot.id.asc()
                )
            )
        ).scalars().all()

    if not rows:
        typer.echo("(no snapshots)")
        return
    for r in rows:
        typer.echo(
            f"#{r.id:>6}  {r.observed_at.isoformat()}  price={r.price} "
            f"status={r.status}  changed={r.changed_fields}"
        )
