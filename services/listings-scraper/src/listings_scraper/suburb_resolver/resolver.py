"""Backward-compat shim — resolver moved to vendor_resolvers.oth.resolver."""
from listings_scraper.vendor_resolvers.oth.resolver import (  # noqa: F401
    _build_slug,
    _fetch_autocomplete,
    _filter_matches,
    _lookup_cached,
    _parse_response,
    _upsert,
    resolve,
)
