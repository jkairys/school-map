"""Listing reconciler — coordination module.

For one batch of OTH search-API results from a `(suburb, category)` job:
1. Upsert each Property by `oth_property_id` (fallback `(address, postcode)`).
2. Find/open a Listing for `(property_id, suburb_id, category)` that is not closed.
3. Diff the latest ListingSnapshot against the new observation.
4. Insert a new ListingSnapshot when the diff is non-empty.
5. Always bump `Listing.last_seen_at`. Always update `agent_name`/`agency_name`.

Soft-expiry sweep (closing stale listings) is NOT in this module — issue 09
ships it. The reconciler never touches `closed_at` / `closure_reason`.
"""
from oth_scraper.listing_reconciler.reconciler import (
    ReconcileResult,
    reconcile_batch,
)

__all__ = ["ReconcileResult", "reconcile_batch"]
