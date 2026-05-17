"""Tests for the producer (POST /scrape-lists/{id}/run) and the read endpoints.

Uses the postgres testcontainer (the queue, listings, and snapshots all rely
on JSONB / postgis types that SQLite can't satisfy).
"""
import asyncio
from datetime import date

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oth_scraper.api.app import app
from oth_scraper.db.engine import get_db, get_session_factory
from oth_scraper.db.models import (
    Listing,
    ListingSnapshot,
    Property,
    ScrapeList,
    ScrapeListSuburb,
    Suburb,
)


@pytest_asyncio.fixture
async def api_client(session_factory: async_sessionmaker[AsyncSession]):
    async def _override_get_db():
        async with session_factory() as s:
            yield s

    def _override_get_session_factory():
        return session_factory

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_session_factory] = _override_get_session_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_suburb(
    factory: async_sessionmaker[AsyncSession],
    name: str,
    postcode: str,
) -> int:
    async with factory() as s:
        async with s.begin():
            row = Suburb(
                name=name,
                postcode=postcode,
                state="QLD",
                oth_slug=f"{name.lower().replace(' ', '-')}-qld-{postcode}",
            )
            s.add(row)
            await s.flush()
            return row.id


async def _seed_list_with_suburbs(
    factory: async_sessionmaker[AsyncSession],
    *,
    name: str = "test list",
    suburb_ids: list[int],
    filters: dict | None = None,
) -> int:
    async with factory() as s:
        async with s.begin():
            row = ScrapeList(
                name=name,
                description=None,
                filters=filters or {},
                cron_schedule=None,
            )
            s.add(row)
            await s.flush()
            list_id = row.id
            for sid in suburb_ids:
                s.add(ScrapeListSuburb(scrape_list_id=list_id, suburb_id=sid))
            await s.flush()
            return list_id


# --------- producer ---------


async def test_run_three_suburb_list_creates_nine_jobs(
    api_client, session_factory
):
    sub_ids = [
        await _seed_suburb(session_factory, f"Sub{i}", f"400{i}")
        for i in range(3)
    ]
    list_id = await _seed_list_with_suburbs(
        session_factory,
        suburb_ids=sub_ids,
        filters={
            "beds_min": 3,
            "beds_max": None,
            "property_types": ["House"],
            "price_min": None,
            "price_max": 1500000,
        },
    )

    r = await api_client.post(f"/scrape-lists/{list_id}/run")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["list_id"] == list_id
    assert body["count"] == 9
    assert len(body["job_ids"]) == 9
    assert len(set(body["job_ids"])) == 9

    # Verify via GET /jobs
    listed = await api_client.get(f"/jobs?list_id={list_id}")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 9
    cats = {r["category"] for r in rows}
    assert cats == {"forsale", "forrent", "recentlysold"}
    pairs = {(r["suburb_id"], r["category"]) for r in rows}
    assert len(pairs) == 9
    assert all(r["status"] == "queued" for r in rows)
    assert all(r["scrape_list_id"] == list_id for r in rows)


async def test_run_snapshot_isolates_jobs_from_list_edits(
    api_client, session_factory
):
    """Editing the list after run() must not mutate jobs' filters."""
    sub_ids = [await _seed_suburb(session_factory, "OnlyOne", "4001")]
    list_id = await _seed_list_with_suburbs(
        session_factory,
        suburb_ids=sub_ids,
        filters={
            "beds_min": 3,
            "beds_max": None,
            "property_types": None,
            "price_min": None,
            "price_max": None,
        },
    )

    r = await api_client.post(f"/scrape-lists/{list_id}/run")
    assert r.status_code == 200
    job_ids = r.json()["job_ids"]
    assert len(job_ids) == 3

    # Edit the list — change filters dramatically.
    upd = await api_client.put(
        f"/scrape-lists/{list_id}",
        json={"filters": {"beds_min": 1, "price_max": 500000}},
    )
    assert upd.status_code == 200

    # Each enqueued job's filters must still reflect the pre-edit list.
    for jid in job_ids:
        got = await api_client.get(f"/jobs/{jid}")
        assert got.status_code == 200
        assert got.json()["filters"]["beds_min"] == 3
        assert got.json()["filters"].get("price_max") is None


async def test_run_missing_list_returns_404(api_client):
    r = await api_client.post("/scrape-lists/9999999/run")
    assert r.status_code == 404


async def test_run_empty_list_returns_zero_jobs(api_client, session_factory):
    list_id = await _seed_list_with_suburbs(session_factory, suburb_ids=[])
    r = await api_client.post(f"/scrape-lists/{list_id}/run")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["job_ids"] == []


# --------- /jobs read ---------


async def test_get_jobs_filter_by_status(api_client, session_factory):
    sub_id = await _seed_suburb(session_factory, "FilterSub", "4002")
    list_id = await _seed_list_with_suburbs(
        session_factory, suburb_ids=[sub_id]
    )
    await api_client.post(f"/scrape-lists/{list_id}/run")

    # Mark one of the jobs succeeded directly so we can filter on status.
    async with session_factory() as s:
        async with s.begin():
            await s.execute(
                text(
                    "UPDATE scrape_job SET status='succeeded' "
                    "WHERE id = (SELECT id FROM scrape_job LIMIT 1)"
                )
            )

    r = await api_client.get("/jobs?status=succeeded")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "succeeded"

    queued = await api_client.get("/jobs?status=queued")
    assert queued.status_code == 200
    assert len(queued.json()) == 2


async def test_get_job_404(api_client):
    r = await api_client.get("/jobs/99999")
    assert r.status_code == 404


async def test_get_jobs_invalid_status_422(api_client):
    r = await api_client.get("/jobs?status=bogus")
    assert r.status_code == 422


# --------- /properties read ---------


async def test_list_properties_filter_by_suburb(api_client, session_factory):
    sub1 = await _seed_suburb(session_factory, "Alpha", "4101")
    sub2 = await _seed_suburb(session_factory, "Bravo", "4102")
    async with session_factory() as s:
        async with s.begin():
            s.add_all(
                [
                    Property(
                        oth_property_id="A-1",
                        formatted_address="1 A St",
                        postcode="4101",
                        suburb_id=sub1,
                    ),
                    Property(
                        oth_property_id="A-2",
                        formatted_address="2 A St",
                        postcode="4101",
                        suburb_id=sub1,
                    ),
                    Property(
                        oth_property_id="B-1",
                        formatted_address="3 B St",
                        postcode="4102",
                        suburb_id=sub2,
                    ),
                ]
            )
            await s.flush()

    r = await api_client.get(f"/properties?suburb={sub1}")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert all(row["suburb_id"] == sub1 for row in rows)
    assert {row["formatted_address"] for row in rows} == {"1 A St", "2 A St"}

    r2 = await api_client.get("/properties?postcode=4102")
    assert r2.status_code == 200
    assert len(r2.json()) == 1
    assert r2.json()[0]["postcode"] == "4102"


async def test_list_properties_latest_sale_date(api_client, session_factory):
    """latest_sale_date is populated for recentlysold listings with a sale_date
    and is null for other categories."""
    sub_id = await _seed_suburb(session_factory, "SaleDateSub", "4110")

    async with session_factory() as s:
        async with s.begin():
            sold_prop = Property(
                oth_property_id="SOLD-1",
                formatted_address="10 Sold St",
                postcode="4110",
                suburb_id=sub_id,
            )
            s.add(sold_prop)
            await s.flush()
            sold_listing = Listing(
                property_id=sold_prop.id,
                suburb_id=sub_id,
                category="recentlysold",
                oth_listing_id="oth-sold-1",
                sale_date=date(2026, 4, 28),
            )
            s.add(sold_listing)
            await s.flush()
            s.add(
                ListingSnapshot(
                    listing_id=sold_listing.id,
                    price=1050000,
                    title="Sold house",
                    blurb=None,
                    bedrooms=4,
                    bathrooms=2,
                    parking=2,
                    land_size_sqm=600,
                    property_type="House",
                    status="sold",
                    raw_payload={"id": "sold-raw"},
                    changed_fields=["__initial__"],
                )
            )

            forsale_prop = Property(
                oth_property_id="SALE-1",
                formatted_address="20 Sale St",
                postcode="4110",
                suburb_id=sub_id,
            )
            s.add(forsale_prop)
            await s.flush()
            forsale_listing = Listing(
                property_id=forsale_prop.id,
                suburb_id=sub_id,
                category="forsale",
                oth_listing_id="oth-sale-1",
            )
            s.add(forsale_listing)
            await s.flush()
            s.add(
                ListingSnapshot(
                    listing_id=forsale_listing.id,
                    price=900000,
                    title="For sale house",
                    blurb=None,
                    bedrooms=3,
                    bathrooms=2,
                    parking=1,
                    land_size_sqm=500,
                    property_type="House",
                    status="available",
                    raw_payload={"id": "sale-raw"},
                    changed_fields=["__initial__"],
                )
            )
            await s.flush()

    r = await api_client.get(f"/properties?suburb={sub_id}")
    assert r.status_code == 200
    rows = r.json()
    by_address = {row["formatted_address"]: row for row in rows}

    sold_row = by_address["10 Sold St"]
    assert sold_row["latest_category"] == "recentlysold"
    assert sold_row["latest_sale_date"] == "2026-04-28"

    forsale_row = by_address["20 Sale St"]
    assert forsale_row["latest_category"] == "forsale"
    assert forsale_row["latest_sale_date"] is None


async def test_list_properties_filter_by_category(api_client, session_factory):
    """category= param returns only properties whose latest_category matches."""
    sub_id = await _seed_suburb(session_factory, "CatFilterSub", "4120")

    async with session_factory() as s:
        async with s.begin():
            # forsale property
            sale_prop = Property(
                oth_property_id="CAT-SALE-1",
                formatted_address="1 Sale Rd",
                postcode="4120",
                suburb_id=sub_id,
            )
            s.add(sale_prop)
            await s.flush()
            sale_listing = Listing(
                property_id=sale_prop.id,
                suburb_id=sub_id,
                category="forsale",
                oth_listing_id="oth-cat-sale",
            )
            s.add(sale_listing)
            await s.flush()
            s.add(
                ListingSnapshot(
                    listing_id=sale_listing.id,
                    price=700000,
                    title="For sale",
                    blurb=None,
                    bedrooms=3,
                    bathrooms=2,
                    parking=1,
                    land_size_sqm=400,
                    property_type="House",
                    status="available",
                    raw_payload={"id": "sale-cat"},
                    changed_fields=["__initial__"],
                )
            )

            # forrent property
            rent_prop = Property(
                oth_property_id="CAT-RENT-1",
                formatted_address="2 Rent Rd",
                postcode="4120",
                suburb_id=sub_id,
            )
            s.add(rent_prop)
            await s.flush()
            rent_listing = Listing(
                property_id=rent_prop.id,
                suburb_id=sub_id,
                category="forrent",
                oth_listing_id="oth-cat-rent",
            )
            s.add(rent_listing)
            await s.flush()
            s.add(
                ListingSnapshot(
                    listing_id=rent_listing.id,
                    price=500,
                    title="For rent",
                    blurb=None,
                    bedrooms=2,
                    bathrooms=1,
                    parking=1,
                    land_size_sqm=None,
                    property_type="Apartment",
                    status="available",
                    raw_payload={"id": "rent-cat"},
                    changed_fields=["__initial__"],
                )
            )

            # recentlysold property
            sold_prop = Property(
                oth_property_id="CAT-SOLD-1",
                formatted_address="3 Sold Rd",
                postcode="4120",
                suburb_id=sub_id,
            )
            s.add(sold_prop)
            await s.flush()
            sold_listing = Listing(
                property_id=sold_prop.id,
                suburb_id=sub_id,
                category="recentlysold",
                oth_listing_id="oth-cat-sold",
                sale_date=date(2026, 1, 15),
            )
            s.add(sold_listing)
            await s.flush()
            s.add(
                ListingSnapshot(
                    listing_id=sold_listing.id,
                    price=820000,
                    title="Recently sold",
                    blurb=None,
                    bedrooms=4,
                    bathrooms=2,
                    parking=2,
                    land_size_sqm=500,
                    property_type="House",
                    status="sold",
                    raw_payload={"id": "sold-cat"},
                    changed_fields=["__initial__"],
                )
            )
            await s.flush()

    # No filter — all three
    r_all = await api_client.get(f"/properties?suburb={sub_id}")
    assert r_all.status_code == 200
    assert len(r_all.json()) == 3

    # forsale filter
    r_sale = await api_client.get(f"/properties?suburb={sub_id}&category=forsale")
    assert r_sale.status_code == 200
    rows = r_sale.json()
    assert len(rows) == 1
    assert rows[0]["latest_category"] == "forsale"
    assert rows[0]["formatted_address"] == "1 Sale Rd"

    # forrent filter
    r_rent = await api_client.get(f"/properties?suburb={sub_id}&category=forrent")
    assert r_rent.status_code == 200
    rows = r_rent.json()
    assert len(rows) == 1
    assert rows[0]["latest_category"] == "forrent"
    assert rows[0]["formatted_address"] == "2 Rent Rd"

    # recentlysold filter
    r_sold = await api_client.get(f"/properties?suburb={sub_id}&category=recentlysold")
    assert r_sold.status_code == 200
    rows = r_sold.json()
    assert len(rows) == 1
    assert rows[0]["latest_category"] == "recentlysold"
    assert rows[0]["formatted_address"] == "3 Sold Rd"


async def test_list_properties_invalid_category_returns_422(api_client):
    """Unknown category value must return 422."""
    r = await api_client.get("/properties?category=invalid")
    assert r.status_code == 422


# --------- /listings read ---------


_seed_counter = 0


async def _seed_property_listing_snapshot(
    factory: async_sessionmaker[AsyncSession],
    *,
    suburb_id: int,
    category: str = "forsale",
    closed: bool = False,
    price: int | None = 800000,
) -> tuple[int, int, int]:
    global _seed_counter
    _seed_counter += 1
    tag = _seed_counter
    async with factory() as s:
        async with s.begin():
            prop = Property(
                oth_property_id=f"prop-{tag}",
                formatted_address=f"{tag} Test St ({category})",
                postcode="4000",
                suburb_id=suburb_id,
            )
            s.add(prop)
            await s.flush()
            listing = Listing(
                property_id=prop.id,
                suburb_id=suburb_id,
                category=category,
                oth_listing_id=f"oth-{prop.id}",
                agent_name="Joe Agent",
                agency_name="Acme Realty",
            )
            s.add(listing)
            await s.flush()
            snap = ListingSnapshot(
                listing_id=listing.id,
                price=price,
                title="Lovely",
                blurb="Charming",
                bedrooms=3,
                bathrooms=2,
                parking=1,
                land_size_sqm=600,
                property_type="House",
                status="available",
                raw_payload={"id": "raw"},
                changed_fields=["__initial__"],
            )
            s.add(snap)
            await s.flush()
            if closed:
                from datetime import datetime, timezone

                listing.closed_at = datetime.now(timezone.utc)
                listing.closure_reason = "withdrawn"
            return prop.id, listing.id, snap.id


async def test_list_listings_active_filter(api_client, session_factory):
    sub_id = await _seed_suburb(session_factory, "ListSub", "4200")
    _, open_id, _ = await _seed_property_listing_snapshot(
        session_factory, suburb_id=sub_id, category="forsale", closed=False
    )
    _, closed_id, _ = await _seed_property_listing_snapshot(
        session_factory, suburb_id=sub_id, category="forsale", closed=True
    )

    r_all = await api_client.get(f"/listings?suburb={sub_id}")
    assert r_all.status_code == 200
    ids = {row["id"] for row in r_all.json()}
    assert ids == {open_id, closed_id}

    r_active = await api_client.get(
        f"/listings?suburb={sub_id}&active=true"
    )
    assert r_active.status_code == 200
    rows = r_active.json()
    assert len(rows) == 1
    assert rows[0]["id"] == open_id
    assert rows[0]["closed_at"] is None


async def test_list_listings_filter_by_category(api_client, session_factory):
    sub_id = await _seed_suburb(session_factory, "CatSub", "4201")
    _, sale_id, _ = await _seed_property_listing_snapshot(
        session_factory, suburb_id=sub_id, category="forsale"
    )
    _, rent_id, _ = await _seed_property_listing_snapshot(
        session_factory, suburb_id=sub_id, category="forrent"
    )

    r = await api_client.get(
        f"/listings?suburb={sub_id}&category=forrent"
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["id"] == rent_id
    assert rows[0]["category"] == "forrent"


async def test_get_listing_includes_latest_snapshot(
    api_client, session_factory
):
    sub_id = await _seed_suburb(session_factory, "DetailSub", "4202")
    _, listing_id, snap_id = await _seed_property_listing_snapshot(
        session_factory, suburb_id=sub_id, price=900000
    )

    # Add a newer snapshot — the endpoint must return the latest.
    async with session_factory() as s:
        async with s.begin():
            newer = ListingSnapshot(
                listing_id=listing_id,
                price=950000,
                title="Updated",
                blurb=None,
                bedrooms=3,
                bathrooms=2,
                parking=1,
                land_size_sqm=600,
                property_type="House",
                status="under-offer",
                raw_payload={"id": "raw-2"},
                changed_fields=["price", "status", "title"],
            )
            s.add(newer)
            await s.flush()
            newer_id = newer.id

    r = await api_client.get(f"/listings/{listing_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == listing_id
    assert body["latest_snapshot"] is not None
    assert body["latest_snapshot"]["id"] == newer_id
    assert body["latest_snapshot"]["price"] == 950000
    assert body["latest_snapshot"]["status"] == "under-offer"


async def test_get_listing_404(api_client):
    r = await api_client.get("/listings/99999")
    assert r.status_code == 404


async def test_listing_snapshots_history(api_client, session_factory):
    sub_id = await _seed_suburb(session_factory, "HistSub", "4203")
    _, listing_id, first_snap_id = await _seed_property_listing_snapshot(
        session_factory, suburb_id=sub_id, price=800000
    )

    async with session_factory() as s:
        async with s.begin():
            for price, status_ in ((850000, "available"), (900000, "sold")):
                s.add(
                    ListingSnapshot(
                        listing_id=listing_id,
                        price=price,
                        title="t",
                        blurb=None,
                        bedrooms=3,
                        bathrooms=2,
                        parking=1,
                        land_size_sqm=600,
                        property_type="House",
                        status=status_,
                        raw_payload={"id": status_},
                        changed_fields=["price"],
                    )
                )
            await s.flush()

    r = await api_client.get(f"/listings/{listing_id}/snapshots")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3
    # Ordered ascending by observed_at — first snapshot first.
    assert rows[0]["id"] == first_snap_id
    assert rows[0]["price"] == 800000
    assert rows[-1]["price"] == 900000


async def test_listing_snapshots_404_for_unknown_listing(api_client):
    r = await api_client.get("/listings/99999/snapshots")
    assert r.status_code == 404


# --------- OpenAPI surface ---------


async def test_openapi_documents_new_endpoints(api_client):
    r = await api_client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    paths = spec["paths"]
    assert "/scrape-lists/{list_id}/run" in paths
    assert "post" in paths["/scrape-lists/{list_id}/run"]
    assert "/jobs" in paths
    assert "/jobs/{job_id}" in paths
    assert "/properties" in paths
    assert "/listings" in paths
    assert "/listings/{listing_id}" in paths
    assert "/listings/{listing_id}/snapshots" in paths


# --------- end-to-end happy path ---------


async def test_e2e_run_drain_query(api_client, session_factory):
    """Create list → add suburb → run → drain via in-process worker (stubbed
    OTH client) → assert listings/snapshots queryable via the read API."""
    sub_id = await _seed_suburb(session_factory, "E2E Sub", "4300")
    list_id = await _seed_list_with_suburbs(
        session_factory,
        name="e2e",
        suburb_ids=[sub_id],
        filters={
            "beds_min": None,
            "beds_max": None,
            "property_types": None,
            "price_min": None,
            "price_max": None,
        },
    )

    r = await api_client.post(f"/scrape-lists/{list_id}/run")
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 3

    # Drive a single worker against a stubbed OTH client that returns one
    # listing on page 0 of the forsale category and empty pages elsewhere.
    import httpx
    from oth_scraper.oth_client import (
        Category,
        ListingFilters,
        OTHListing,
        ResolvedSuburb,
        SearchPage,
    )
    from oth_scraper.queue import JobQueue
    from oth_scraper.worker_loop import run_worker

    sample_payload = {
        "oth_property_id": "PROP-E2E-1",
        "formatted_address": "10 E2E St",
        "postcode": "4300",
        "price": 875000,
        "title": "E2E house",
        "blurb": "test",
        "bedrooms": 4,
        "bathrooms": 2,
        "parking": 2,
        "land_size_sqm": 700,
        "property_type": "House",
        "status": "available",
    }

    class _Session:
        def __init__(self) -> None:
            self._client = httpx.AsyncClient()

        async def http(self) -> httpx.AsyncClient:
            return self._client

        async def rotate(self) -> None:  # pragma: no cover - not exercised
            pass

        async def close(self) -> None:
            await self._client.aclose()

    class _Client:
        async def search(
            self,
            suburb: ResolvedSuburb,
            category: Category,
            filters: ListingFilters,
            page: int,
            http: httpx.AsyncClient,
        ) -> SearchPage:
            if category is Category.FORSALE and page == 0:
                listing = OTHListing(**sample_payload)
                return SearchPage(
                    listings=[listing],
                    raw_payloads=[sample_payload],
                    total=1,
                    page=0,
                    has_next=False,
                )
            return SearchPage(
                listings=[], raw_payloads=[], total=0, page=page, has_next=False
            )

    async def _no_sweep(*_a, **_kw) -> int:
        return 0

    queue = JobQueue(
        session_factory,
        max_retries_transient=3,
        max_retries_antibot=1,
        max_retries_parse=0,
        reclaim_ttl_seconds=600,
    )
    scrape_session = _Session()
    shutdown = asyncio.Event()
    worker = asyncio.create_task(
        run_worker(
            queue=queue,
            session_factory=session_factory,
            oth_client=_Client(),
            scrape_session=scrape_session,
            concurrency=1,
            poll_interval_s=0.05,
            shutdown_grace_s=5.0,
            install_signal_handlers=False,
            shutdown_event=shutdown,
            soft_expiry_sweep=_no_sweep,
        )
    )

    try:
        deadline = asyncio.get_event_loop().time() + 10.0
        while True:
            async with session_factory() as s:
                done = (
                    await s.execute(
                        text(
                            "SELECT count(*) FROM scrape_job "
                            "WHERE status = 'succeeded'"
                        )
                    )
                ).scalar_one()
            if done >= 3:
                break
            if asyncio.get_event_loop().time() > deadline:
                raise AssertionError(f"only {done} jobs succeeded in time")
            await asyncio.sleep(0.05)
    finally:
        shutdown.set()
        await asyncio.wait_for(worker, timeout=10.0)
        await scrape_session.close()

    # Read API should now surface the listing and its initial snapshot.
    listings_resp = await api_client.get(
        f"/listings?suburb={sub_id}&category=forsale&active=true"
    )
    assert listings_resp.status_code == 200
    listings = listings_resp.json()
    assert len(listings) == 1
    listing_id = listings[0]["id"]

    detail = await api_client.get(f"/listings/{listing_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["latest_snapshot"] is not None
    assert body["latest_snapshot"]["price"] == 875000

    snaps = await api_client.get(f"/listings/{listing_id}/snapshots")
    assert snaps.status_code == 200
    assert len(snaps.json()) == 1

    props = await api_client.get(f"/properties?suburb={sub_id}")
    assert props.status_code == 200
    assert len(props.json()) == 1
    assert props.json()[0]["formatted_address"] == "10 E2E St"
