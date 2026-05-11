"""Extract the settled-sale date from an OTH recentlysold raw_payload.

Key path discovery
------------------
OTH's search API returns `recentlysold` listings with a `lastSale` object
that carries the sale date at `lastSale.eventDate` as an ISO-8601 date string
(e.g. ``"2026-04-28"``).  Confirmed as the consistent, sole key across all 24
entries in the ``recentlysold_paddington_p0.json`` fixture corpus.  The key is
absent from ``forsale`` and ``forrent`` fixture corpora.

Usage
-----
This module exposes a single pure function ``extract_sale_date`` — no async,
no DB session, no I/O — so it is trivially unit-testable and can be called
from any synchronous context inside the reconciler.

    >>> from oth_scraper.sale_date_extractor import extract_sale_date
    >>> extract_sale_date({"lastSale": {"eventDate": "2026-04-28"}})
    datetime.date(2026, 4, 28)
    >>> extract_sale_date({}) is None
    True
    >>> extract_sale_date({"lastSale": {"eventDate": "not-a-date"}}) is None
    True
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# Ordered list of candidate key paths to try (outer_key, inner_key).
# The first non-None, parseable value wins.  A second candidate is provided
# as a defensive fallback in case OTH ever aliases the field.
_CANDIDATE_PATHS: list[tuple[str, str]] = [
    ("lastSale", "eventDate"),
]


def extract_sale_date(raw_payload: dict[str, Any]) -> date | None:
    """Return the settled-sale date from an OTH ``recentlysold`` raw payload.

    Tries each candidate key path in ``_CANDIDATE_PATHS`` in order. Returns
    the first successfully parsed ``datetime.date`` value, or ``None`` when:

    - the payload is empty or missing the expected keys
    - the value is present but not a parseable ISO-8601 date string
    - any unexpected exception occurs during parsing

    This function is **pure** — no database access, no I/O, no async.

    Args:
        raw_payload: The verbatim OTH JSON dict stored in
            ``listing_snapshot.raw_payload``.  For ``forsale``/``forrent``
            payloads the relevant keys are absent and ``None`` is returned.

    Returns:
        A ``datetime.date`` instance, or ``None``.
    """
    for outer_key, inner_key in _CANDIDATE_PATHS:
        outer = raw_payload.get(outer_key)
        if not isinstance(outer, dict):
            continue
        raw_value = outer.get(inner_key)
        if raw_value is None:
            continue
        parsed = _parse_date(raw_value)
        if parsed is not None:
            return parsed

    return None


def _parse_date(value: Any) -> date | None:
    """Parse an ISO-8601 date string (``YYYY-MM-DD``) to a ``date``.

    Only accepts ``str`` values — non-string types (int, float, etc.) are
    rejected and ``None`` is returned.  Returns ``None`` on any parse error
    rather than raising, so callers never have to guard against malformed OTH
    data.
    """
    if not isinstance(value, str):
        logger.debug(
            "sale_date_extractor: expected str for date value, got %r", type(value).__name__
        )
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        logger.debug("sale_date_extractor: could not parse %r as a date: %s", value, exc)
        return None
