"""Extract the __NEXT_DATA__ JSON payload embedded in Domain search pages.

Domain's search results are server-side rendered via Next.js. The full
page data is serialised into a `<script id="__NEXT_DATA__" type="application/json">`
tag in the HTML. This module provides the pure function that finds and
parses that tag.

Deep module — no I/O, no DB, no camoufox. Input: raw HTML string.
Output: parsed dict or raises ParseError.
"""

import json
import re
from typing import Any

from listings_scraper.vendor_clients.domain.exceptions import ParseError

# Matches the __NEXT_DATA__ script tag content.
# Domain inlines it as: <script id="__NEXT_DATA__" type="application/json">...</script>
_NEXT_DATA_RE = re.compile(
    r'<script\s[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)


def extract_next_data(html: str) -> dict[str, Any]:
    """Find and parse the __NEXT_DATA__ JSON embedded in a Domain page.

    Args:
        html: Full HTML body of a Domain search page (from page.content()).

    Returns:
        The parsed __NEXT_DATA__ dict.

    Raises:
        ParseError: If the script tag is not found or the JSON is invalid.
    """
    match = _NEXT_DATA_RE.search(html)
    if match is None:
        raise ParseError(
            "Could not find <script id='__NEXT_DATA__'> in Domain page HTML. "
            "The page structure may have changed, or anti-bot blocked the response."
        )
    json_text = match.group(1).strip()
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ParseError(
            f"__NEXT_DATA__ JSON is invalid: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ParseError(
            f"__NEXT_DATA__ parsed to {type(data).__name__}, expected dict"
        )
    return data
