"""Listing reconciler — coordination module.

For one batch of OTH search-API results from a `(suburb, category)` job:
1. Upsert each Property by `oth_property_id` (fallback `(address, postcode)`).
2. Find/open a Listing for `(property_id, suburb_id, category)` that is not closed.
3. Diff the latest ListingSnapshot against the new observation.
4. Insert a new ListingSnapshot when the diff is non-empty.
5. Always bump `Listing.last_seen_at`. Always update `agent_name`/`agency_name`.

Soft-expiry sweep (closing stale listings) lives in `soft_expiry` and is
invoked by the worker loop AFTER a successful job — never from inside
`reconcile_batch`, which only sees one page at a time.
"""
from listings_scraper.listing_reconciler.reconciler import (
    ReconcileResult,
    reconcile_batch,
)
from listings_scraper.listing_reconciler.soft_expiry import run_soft_expiry_sweep

__all__ = ["ReconcileResult", "reconcile_batch", "run_soft_expiry_sweep"]
