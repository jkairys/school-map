"""Core scraper class for Brisbane property data."""

import asyncio
import random
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser

from .config import (
    BASE_URL, DEFAULT_MIN_DELAY, DEFAULT_MAX_DELAY,
    JS_DIR, load_suburbs
)
from .models import SoldProperty
from .parsers import parse_price, parse_sold_date, is_within_date_range
from .storage import SuburbStorage


class BrisbanePropertyScraper:
    """Scraper for sold property data from onthehouse.com.au using Playwright."""

    def __init__(
        self,
        min_delay: float = DEFAULT_MIN_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        headless: bool = True
    ):
        """Initialize the scraper with configurable delays.

        Args:
            min_delay: Minimum delay between requests in seconds
            max_delay: Maximum delay between requests in seconds
            headless: Whether to run browser in headless mode
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.headless = headless
        self.suburbs = load_suburbs()

        # Load JavaScript files
        self._listings_js = (JS_DIR / "extract_listings.js").read_text()
        self._details_js = (JS_DIR / "extract_details.js").read_text()

    async def _random_delay(self, multiplier: float = 1.0):
        """Add a random delay between requests to avoid rate limiting.

        Args:
            multiplier: Multiply the delay by this factor
        """
        delay = random.uniform(self.min_delay, self.max_delay) * multiplier
        await asyncio.sleep(delay)

    def _build_search_url(self, suburb: str, postcode: str, page: int = 1) -> str:
        """Build the search URL for sold listings in a suburb.

        Args:
            suburb: Suburb name (hyphenated)
            postcode: Suburb postcode
            page: Page number

        Returns:
            Full URL for the search page
        """
        base = f"{BASE_URL}/sold/qld/{suburb}-{postcode}"
        if page > 1:
            return f"{base}?page={page}"
        return base

    async def _fetch_property_details(self, page: Page, prop: SoldProperty) -> SoldProperty:
        """Fetch additional details (land size, description) from individual property page.

        Args:
            page: Playwright page instance
            prop: SoldProperty object to update

        Returns:
            Updated SoldProperty object
        """
        if not prop.listing_url:
            return prop

        try:
            await page.goto(prop.listing_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # Extract details using JavaScript
            details = await page.evaluate(self._details_js)

            # Update property with fetched details
            if details.get('landSize'):
                prop.land_size_sqm = details['landSize']
            if details.get('description'):
                prop.description = details['description']
            # Only update bed/bath/parking if we didn't have them
            if prop.bedrooms is None and details.get('beds'):
                prop.bedrooms = details['beds']
            if prop.bathrooms is None and details.get('baths'):
                prop.bathrooms = details['baths']
            if prop.parking is None and details.get('parking'):
                prop.parking = details['parking']

        except Exception as e:
            print(f"  Error fetching details for {prop.address}: {e}")

        return prop

    async def _scrape_listings_from_page(self, page: Page, suburb: str, postcode: str) -> list[SoldProperty]:
        """Extract listing data directly from the rendered page using specific selectors.

        Args:
            page: Playwright page instance
            suburb: Suburb name (hyphenated)
            postcode: Suburb postcode

        Returns:
            List of SoldProperty objects found on the page
        """
        properties = []

        try:
            await page.wait_for_selector('[class*="PropertyCardSearch__propertyCard"]', timeout=15000, state="attached")
        except Exception as e:
            print(f"Could not find property cards: {e}")

        # Extract data using JavaScript
        listings_data = await page.evaluate(self._listings_js)

        # Deduplicate within page
        seen_urls = set()
        unique_listings = []
        for listing in listings_data:
            url = listing.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_listings.append(listing)

        print(f"  Extracted {len(unique_listings)} unique listings (from {len(listings_data)} total)")

        for listing in unique_listings:
            sold_date = parse_sold_date(listing.get('soldDate', ''))

            beds = listing.get('beds')
            if beds is not None and (beds < 3 or beds > 4):
                continue

            prop_type = listing.get('propertyType', 'House')
            if prop_type.lower() not in ['house']:
                continue

            prop = SoldProperty(
                address=listing.get('address', ''),
                suburb=suburb.replace("-", " ").title(),
                postcode=postcode,
                sale_price=parse_price(listing.get('price')),
                sale_date=sold_date,
                bedrooms=beds,
                bathrooms=listing.get('baths'),
                parking=listing.get('parking'),
                land_size_sqm=None,
                property_type=prop_type,
                description='',
                listing_url=listing.get('url', ''),
                agent_name=listing.get('agentName'),
                agency_name=listing.get('agencyName'),
            )

            if is_within_date_range(prop.sale_date, days=90):
                properties.append(prop)

        return properties

    async def scrape_suburb(
        self,
        suburb: str,
        storage: SuburbStorage,
        max_pages: int = 5,
        fetch_details: bool = True,
        save_incrementally: bool = True
    ) -> list[SoldProperty]:
        """Scrape sold property listings for a single suburb with incremental saving.

        Args:
            suburb: Suburb name (use hyphens, e.g., "paddington" or "st-lucia")
            storage: SuburbStorage instance for saving data
            max_pages: Maximum number of result pages to scrape
            fetch_details: Whether to fetch land size from individual property pages
            save_incrementally: Whether to save after each page

        Returns:
            List of SoldProperty objects
        """
        suburb_key = suburb.lower().replace(" ", "-")

        postcode = self.suburbs.get(suburb_key)
        if not postcode:
            print(f"Unknown suburb: {suburb}. Please provide postcode.")
            return []

        all_properties = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            page_num = 1
            while page_num <= max_pages:
                url = self._build_search_url(suburb_key, postcode, page_num)
                print(f"  Fetching page {page_num}: {url}")

                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(3)

                    properties = await self._scrape_listings_from_page(page, suburb_key, postcode)

                    if properties:
                        existing_urls = {p.listing_url for p in all_properties}
                        new_properties = [p for p in properties if p.listing_url not in existing_urls]
                        print(f"  Found {len(new_properties)} new matching listings")
                        all_properties.extend(new_properties)
                    else:
                        print(f"  No matching listings found on page {page_num}")
                        if page_num > 1:
                            break

                    next_link = await page.query_selector('a[rel="next"], [class*="pagination"] a[href*="page="]')
                    if not next_link:
                        break

                    page_num += 1
                    await self._random_delay()

                except Exception as e:
                    print(f"  Error fetching page {page_num}: {e}")
                    break

            # Fetch details for each property if requested
            if fetch_details and all_properties:
                print(f"  Fetching details for {len(all_properties)} properties...")
                for i, prop in enumerate(all_properties):
                    print(f"    [{i+1}/{len(all_properties)}] {prop.address}")
                    await self._fetch_property_details(page, prop)
                    await self._random_delay(0.5)

            await browser.close()

        # Save all properties
        if all_properties:
            storage.save(all_properties)
            print(f"  Saved {len(all_properties)} properties to {storage.filename}")

        return all_properties
