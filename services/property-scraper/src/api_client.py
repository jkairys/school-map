"""API client for OnTheHouse property data."""

import asyncio
import json
from typing import Optional
from dataclasses import dataclass

import httpx
from playwright.async_api import Page


API_URL = "https://www.onthehouse.com.au/odin/api/composite/search"

DEFAULT_HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "origin": "https://www.onthehouse.com.au",
}


@dataclass
class APIResponse:
    """Response from the OnTheHouse API."""
    content: list[dict]
    total_elements: int
    total_pages: int
    page_number: int
    page_size: int

    @classmethod
    def from_json(cls, data: dict) -> "APIResponse":
        return cls(
            content=data.get("content", []),
            total_elements=data.get("totalElements", 0),
            total_pages=data.get("totalPages", 0),
            page_number=data.get("number", 0),
            page_size=data.get("size", 0),
        )


def build_search_payload(
    suburb: str,
    postcode: str,
    state: str = "QLD",
    page: int = 0,
    size: int = 24,
) -> dict:
    """Build the search request payload.

    Args:
        suburb: Suburb name (space-separated, e.g., "wynnum west")
        postcode: Suburb postcode
        state: State code (default: QLD)
        page: Page number (0-indexed)
        size: Number of results per page

    Returns:
        Request payload dict
    """
    return {
        "size": size,
        "number": page,
        "sort": [{"lastSale.eventDate": "desc"}],
        "query": {
            "queries": [{
                "category": "RecentlySold",
                "stateCode": state,
                "suburb": suburb,
                "postCode": postcode,
            }]
        }
    }


async def fetch_via_http(
    suburb: str,
    postcode: str,
    page: int = 0,
    size: int = 24,
    timeout: float = 30.0,
) -> APIResponse:
    """Fetch property data directly via HTTP.

    Args:
        suburb: Suburb name (space-separated)
        postcode: Suburb postcode
        page: Page number (0-indexed)
        size: Results per page
        timeout: Request timeout in seconds

    Returns:
        APIResponse with property data

    Raises:
        httpx.HTTPError: On HTTP errors
    """
    payload = build_search_payload(suburb, postcode, page=page, size=size)
    headers = {
        **DEFAULT_HEADERS,
        "referer": f"https://www.onthehouse.com.au/sold/qld/{suburb.replace(' ', '-')}-{postcode}",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            API_URL,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        return APIResponse.from_json(response.json())


async def fetch_via_playwright(
    page: Page,
    suburb: str,
    postcode: str,
    page_num: int = 0,
    size: int = 24,
) -> APIResponse:
    """Fetch property data via Playwright browser context.

    Uses page.evaluate to make a fetch request from within the browser,
    maintaining the browser's session and fingerprint.

    Args:
        page: Playwright page instance
        suburb: Suburb name (space-separated)
        postcode: Suburb postcode
        page_num: Page number (0-indexed)
        size: Results per page

    Returns:
        APIResponse with property data
    """
    payload = build_search_payload(suburb, postcode, page=page_num, size=size)

    # First navigate to the site to establish session/cookies if needed
    suburb_slug = suburb.replace(" ", "-")
    site_url = f"https://www.onthehouse.com.au/sold/qld/{suburb_slug}-{postcode}"

    # Check if we're already on the site
    current_url = page.url
    if "onthehouse.com.au" not in current_url:
        await page.goto(site_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1)

    # Make the API call from within the browser
    js_code = """
    async (payload) => {
        const response = await fetch('https://www.onthehouse.com.au/odin/api/composite/search', {
            method: 'POST',
            headers: {
                'accept': 'application/json',
                'content-type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return await response.json();
    }
    """

    result = await page.evaluate(js_code, payload)
    return APIResponse.from_json(result)


class OnTheHouseAPI:
    """Client for OnTheHouse API with automatic fallback."""

    def __init__(self, use_fallback: bool = True):
        """Initialize the API client.

        Args:
            use_fallback: Whether to fall back to Playwright on HTTP errors
        """
        self.use_fallback = use_fallback
        self._http_failed = False
        self._playwright_page: Optional[Page] = None

    def set_playwright_page(self, page: Page):
        """Set the Playwright page for fallback requests."""
        self._playwright_page = page

    async def fetch(
        self,
        suburb: str,
        postcode: str,
        page: int = 0,
        size: int = 24,
    ) -> APIResponse:
        """Fetch property data, with automatic fallback.

        Tries direct HTTP first. If that fails and fallback is enabled,
        uses Playwright to make the request from within the browser.

        Args:
            suburb: Suburb name (space-separated, e.g., "wynnum west")
            postcode: Suburb postcode
            page: Page number (0-indexed)
            size: Results per page

        Returns:
            APIResponse with property data
        """
        # Try direct HTTP first (unless it's already failed)
        if not self._http_failed:
            try:
                return await fetch_via_http(suburb, postcode, page=page, size=size)
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                if self.use_fallback and self._playwright_page:
                    print(f"  Direct HTTP failed ({e}), falling back to Playwright...")
                    self._http_failed = True
                else:
                    raise

        # Use Playwright fallback
        if self._playwright_page:
            return await fetch_via_playwright(
                self._playwright_page,
                suburb,
                postcode,
                page_num=page,
                size=size,
            )

        raise RuntimeError("HTTP failed and no Playwright page available for fallback")
