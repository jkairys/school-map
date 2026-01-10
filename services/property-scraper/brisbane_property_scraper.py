#!/usr/bin/env python3
"""
Brisbane Property Sold Data Scraper

Scrapes sold property data from onthehouse.com.au for Brisbane metropolitan suburbs.
Uses Playwright for browser automation to bypass anti-bot measures.
Filters for 3-4 bedroom houses, sold in the last 3 months.
"""

import json
import re
import asyncio
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser


@dataclass
class SoldProperty:
    """Represents a sold property with key details."""
    address: str
    suburb: str
    postcode: str
    sale_price: Optional[int]
    sale_date: Optional[str]
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    parking: Optional[int]
    land_size_sqm: Optional[int]
    property_type: str
    description: str
    listing_url: str
    agent_name: Optional[str]
    agency_name: Optional[str]


class BrisbanePropertyScraper:
    """Scraper for sold property data from onthehouse.com.au using Playwright."""

    BASE_URL = "https://www.onthehouse.com.au"

    # Brisbane metropolitan suburbs with postcodes
    BRISBANE_SUBURBS = {
        # Inner Brisbane
        "paddington": "4064",
        "red-hill": "4059",
        "kelvin-grove": "4059",
        "new-farm": "4005",
        "teneriffe": "4005",
        "fortitude-valley": "4006",
        "west-end": "4101",
        "south-brisbane": "4101",
        "woolloongabba": "4102",
        "kangaroo-point": "4169",
        "east-brisbane": "4169",
        "highgate-hill": "4101",
        "milton": "4064",
        "petrie-terrace": "4000",
        "spring-hill": "4000",
        "herston": "4006",
        "newstead": "4006",
        "bowen-hills": "4006",

        # Northern suburbs
        "chermside": "4032",
        "kedron": "4031",
        "stafford": "4053",
        "stafford-heights": "4053",
        "everton-park": "4053",
        "mitchelton": "4053",
        "aspley": "4034",
        "geebung": "4034",
        "zillmere": "4034",
        "bracken-ridge": "4017",
        "sandgate": "4017",
        "shorncliffe": "4017",
        "brighton": "4017",
        "deagon": "4017",
        "nundah": "4012",
        "wavell-heights": "4012",
        "northgate": "4013",
        "banyo": "4014",
        "nudgee": "4014",
        "virginia": "4014",
        "albany-creek": "4035",
        "bridgeman-downs": "4035",
        "mcDowall": "4053",
        "everton-hills": "4053",
        "arana-hills": "4054",

        # Southern suburbs
        "mount-gravatt": "4122",
        "mount-gravatt-east": "4122",
        "holland-park": "4121",
        "holland-park-west": "4121",
        "tarragindi": "4121",
        "annerley": "4103",
        "greenslopes": "4120",
        "coorparoo": "4151",
        "camp-hill": "4152",
        "carindale": "4152",
        "carina": "4152",
        "carina-heights": "4152",
        "sunnybank": "4109",
        "sunnybank-hills": "4109",
        "robertson": "4109",
        "eight-mile-plains": "4113",
        "macgregor": "4109",
        "mansfield": "4122",
        "wishart": "4122",
        "upper-mount-gravatt": "4122",
        "rochedale-south": "4123",

        # Western suburbs
        "indooroopilly": "4068",
        "st-lucia": "4067",
        "toowong": "4066",
        "auchenflower": "4066",
        "bardon": "4065",
        "ashgrove": "4060",
        "the-gap": "4061",
        "keperra": "4054",
        "ferny-grove": "4055",
        "fig-tree-pocket": "4069",
        "kenmore": "4069",
        "kenmore-hills": "4069",
        "chapel-hill": "4069",
        "brookfield": "4069",
        "pullenvale": "4069",
        "taringa": "4068",
        "graceville": "4075",
        "sherwood": "4075",
        "corinda": "4075",
        "oxley": "4075",

        # Eastern suburbs
        "wynnum": "4178",
        "wynnum-west": "4178",
        "manly": "4179",
        "manly-west": "4179",
        "lota": "4179",
        "capalaba": "4157",
        "cleveland": "4163",
        "victoria-point": "4165",
        "thornlands": "4164",
        "birkdale": "4159",
        "wellington-point": "4160",
        "ormiston": "4160",
        "thorneside": "4158",
        "cannon-hill": "4170",
        "morningside": "4170",
        "bulimba": "4171",
        "hawthorne": "4171",
        "balmoral": "4171",
        "murarrie": "4172",

        # Moreton Bay region
        "redcliffe": "4020",
        "margate": "4019",
        "scarborough": "4020",
        "clontarf": "4019",
        "woody-point": "4019",
        "north-lakes": "4509",
        "mango-hill": "4509",
        "kallangur": "4503",
        "petrie": "4502",
        "strathpine": "4500",
        "brendale": "4500",
        "warner": "4500",
        "cashmere": "4500",
        "lawnton": "4501",
        "griffin": "4503",
        "murrumba-downs": "4503",
        "deception-bay": "4508",
        "rothwell": "4022",
        "kippa-ring": "4021",

        # Logan/Gold Coast corridor
        "springwood": "4127",
        "underwood": "4119",
        "slacks-creek": "4127",
        "logan-central": "4114",
        "beenleigh": "4207",
        "ormeau": "4208",
        "pimpama": "4209",
        "coomera": "4209",
        "upper-coomera": "4209",
        "helensvale": "4212",
        "pacific-pines": "4211",
        "southport": "4215",
        "surfers-paradise": "4217",
        "broadbeach": "4218",
        "burleigh-heads": "4220",
        "palm-beach": "4221",
        "currumbin": "4223",
        "coolangatta": "4225",
        "robina": "4226",
        "varsity-lakes": "4227",
        "mudgeeraba": "4213",
        "nerang": "4211",
        "labrador": "4215",
        "runaway-bay": "4216",
        "hope-island": "4212",
    }

    def __init__(self, min_delay: float = 2.0, max_delay: float = 5.0, headless: bool = True):
        """Initialize the scraper with configurable delays."""
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.headless = headless
        self.browser: Optional[Browser] = None

    async def _random_delay(self, multiplier: float = 1.0):
        """Add a random delay between requests to avoid rate limiting."""
        delay = random.uniform(self.min_delay, self.max_delay) * multiplier
        await asyncio.sleep(delay)

    def _build_search_url(self, suburb: str, postcode: str, page: int = 1) -> str:
        """Build the search URL for sold listings in a suburb."""
        base = f"{self.BASE_URL}/sold/qld/{suburb}-{postcode}"
        if page > 1:
            return f"{base}?page={page}"
        return base

    def _parse_price(self, price_str: Optional[str]) -> Optional[int]:
        """Parse a price string into an integer."""
        if not price_str:
            return None
        if "not available" in price_str.lower():
            return None

        cleaned = re.sub(r'[^\d]', '', price_str)
        if cleaned:
            try:
                return int(cleaned)
            except ValueError:
                return None
        return None

    def _parse_sold_date(self, text: str) -> Optional[str]:
        """Extract sold date from ribbon text like 'Sold on 23 Dec 2025'."""
        match = re.search(r'Sold\s+(?:on\s+)?(\d{1,2}\s+\w+\s+\d{4})', text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _parse_land_size(self, text: str) -> Optional[int]:
        """Extract land size in sqm from text."""
        if not text:
            return None
        # Look for patterns like "650 m²", "650m2", "650 sqm", "Land Size: 650"
        match = re.search(r'(\d+(?:,\d+)?)\s*(?:m²|m2|sqm|square\s*m)', text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1).replace(',', ''))
            except ValueError:
                return None
        return None

    def _is_within_last_3_months(self, date_str: Optional[str]) -> bool:
        """Check if a date string is within the last 3 months."""
        if not date_str:
            return True

        three_months_ago = datetime.now() - timedelta(days=90)

        date_formats = [
            "%d %b %Y",
            "%d %B %Y",
            "%Y-%m-%d",
            "%d/%m/%Y",
        ]

        for fmt in date_formats:
            try:
                sale_date = datetime.strptime(date_str.strip(), fmt)
                return sale_date >= three_months_ago
            except ValueError:
                continue

        return True

    async def _fetch_property_details(self, page: Page, prop: SoldProperty) -> SoldProperty:
        """Fetch additional details (land size, description) from individual property page."""
        if not prop.listing_url:
            return prop

        try:
            await page.goto(prop.listing_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # Extract details using JavaScript
            details = await page.evaluate('''
                () => {
                    const result = {
                        landSize: null,
                        description: '',
                        beds: null,
                        baths: null,
                        parking: null
                    };

                    // Look for land size in various places
                    const pageText = document.body.textContent || '';

                    // Try to find land size - look for "Land Size" or "Land Area" labels
                    const landMatch = pageText.match(/(?:Land\\s*(?:Size|Area)|Block\\s*Size)[:\\s]*([\\d,]+)\\s*(?:m²|m2|sqm)/i);
                    if (landMatch) {
                        result.landSize = parseInt(landMatch[1].replace(/,/g, ''));
                    }

                    // Also try property attributes section
                    const attrElements = document.querySelectorAll('[class*="PropertyAttribute"], [class*="property-attribute"], [class*="feature"]');
                    attrElements.forEach(el => {
                        const text = el.textContent || '';
                        if (text.match(/land/i) && !result.landSize) {
                            const match = text.match(/(\\d+(?:,\\d+)?)\\s*(?:m²|m2|sqm)/i);
                            if (match) {
                                result.landSize = parseInt(match[1].replace(/,/g, ''));
                            }
                        }
                    });

                    // Try finding in a details/specs table
                    const specRows = document.querySelectorAll('tr, [class*="spec"], [class*="detail"]');
                    specRows.forEach(row => {
                        const text = row.textContent || '';
                        if (text.match(/land/i) && !result.landSize) {
                            const match = text.match(/(\\d+(?:,\\d+)?)\\s*(?:m²|m2|sqm)?/);
                            if (match && parseInt(match[1].replace(/,/g, '')) > 100) {
                                result.landSize = parseInt(match[1].replace(/,/g, ''));
                            }
                        }
                    });

                    // Get description
                    const descEl = document.querySelector('[class*="description"], [class*="Description"], .property-description, #description');
                    if (descEl) {
                        result.description = descEl.textContent.trim().substring(0, 1000);
                    }

                    // Try to get more accurate bed/bath/parking from detail page
                    const bedsMatch = pageText.match(/(?:Bedrooms?|Beds?)[:\\s]*(\\d+)/i);
                    const bathsMatch = pageText.match(/(?:Bathrooms?|Baths?)[:\\s]*(\\d+)/i);
                    const parkingMatch = pageText.match(/(?:Car\\s*(?:Spaces?|Parks?)|Parking|Garage)[:\\s]*(\\d+)/i);

                    if (bedsMatch) result.beds = parseInt(bedsMatch[1]);
                    if (bathsMatch) result.baths = parseInt(bathsMatch[1]);
                    if (parkingMatch) result.parking = parseInt(parkingMatch[1]);

                    return result;
                }
            ''')

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
        """Extract listing data directly from the rendered page using specific selectors."""
        properties = []

        try:
            await page.wait_for_selector('[class*="PropertyCardSearch__propertyCard"]', timeout=15000, state="attached")
        except Exception as e:
            print(f"Could not find property cards: {e}")

        # Extract data using JavaScript
        listings_data = await page.evaluate('''
            () => {
                const listings = [];
                const cards = document.querySelectorAll('[class*="PropertyCardSearch__propertyCard--"]');

                cards.forEach((card, index) => {
                    try {
                        const listing = {
                            url: '',
                            address: '',
                            price: '',
                            beds: null,
                            baths: null,
                            parking: null,
                            soldDate: '',
                            propertyType: 'House',
                            agentName: '',
                            agencyName: ''
                        };

                        const link = card.querySelector('a[href*="/property/"]');
                        if (link) {
                            listing.url = link.href;
                        }

                        const ribbon = card.querySelector('[class*="recentlySold"]');
                        if (ribbon) {
                            listing.soldDate = ribbon.textContent.trim();
                        }

                        const priceEl = card.querySelector('[class*="propertyCardPrice"]');
                        if (priceEl) {
                            listing.price = priceEl.textContent.trim();
                        }

                        const addressEls = card.querySelectorAll('[class*="propertyCardAddressText"]');
                        if (addressEls.length > 0) {
                            listing.address = Array.from(addressEls).map(el => el.textContent.trim()).join(' ').replace(/,\\s*$/, '');
                        }

                        const attrsEl = card.querySelector('[class*="propertyCardAttributes"]');
                        if (attrsEl) {
                            const bedsMatch = attrsEl.textContent.match(/Bedrooms[:\\s]*?(\\d+)/i);
                            const bathsMatch = attrsEl.textContent.match(/Bathrooms[:\\s]*?(\\d+)/i);
                            const carsMatch = attrsEl.textContent.match(/Car\\s*spaces[:\\s]*?(\\d+)/i);

                            if (bedsMatch) listing.beds = parseInt(bedsMatch[1]);
                            if (bathsMatch) listing.baths = parseInt(bathsMatch[1]);
                            if (carsMatch) listing.parking = parseInt(carsMatch[1]);
                        }

                        const typeMatch = card.textContent.match(/Type[:\\s]*?(House|Apartment|Townhouse|Land|Unit)/i);
                        if (typeMatch) {
                            listing.propertyType = typeMatch[1];
                        }

                        const agentEl = card.querySelector('[class*="agentRep"]');
                        if (agentEl) {
                            const nameEl = agentEl.querySelector('.bold500, [class*="bold"]');
                            if (nameEl) {
                                listing.agentName = nameEl.textContent.trim();
                            }
                            const agencyEl = agentEl.querySelector('[class*="agencyName"]');
                            if (agencyEl) {
                                listing.agencyName = agencyEl.textContent.trim();
                            }
                        }

                        if (listing.address || listing.url) {
                            listings.push(listing);
                        }
                    } catch (e) {
                        console.error('Error parsing card ' + index + ': ' + e);
                    }
                });

                return listings;
            }
        ''')

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
            sold_date = self._parse_sold_date(listing.get('soldDate', ''))

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
                sale_price=self._parse_price(listing.get('price')),
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

            if self._is_within_last_3_months(prop.sale_date):
                properties.append(prop)

        return properties

    async def scrape_suburb(
        self,
        suburb: str,
        postcode: Optional[str] = None,
        max_pages: int = 5,
        fetch_details: bool = True,
        browser_context=None,
        page=None
    ) -> list[SoldProperty]:
        """
        Scrape sold property listings for a single suburb.

        Args:
            suburb: Suburb name (use hyphens, e.g., "paddington" or "st-lucia")
            postcode: Optional postcode (will be looked up if not provided)
            max_pages: Maximum number of result pages to scrape
            fetch_details: Whether to fetch land size from individual property pages
            browser_context: Optional existing browser context to reuse
            page: Optional existing page to reuse

        Returns:
            List of SoldProperty objects
        """
        suburb_key = suburb.lower().replace(" ", "-")

        if not postcode:
            postcode = self.BRISBANE_SUBURBS.get(suburb_key)
            if not postcode:
                print(f"Unknown suburb: {suburb}. Please provide postcode.")
                return []

        all_properties = []
        own_browser = browser_context is None

        async with async_playwright() as p:
            if own_browser:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                page = await context.new_page()
            else:
                context = browser_context
                browser = None

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

            if own_browser and browser:
                await browser.close()

        return all_properties

    async def scrape_multiple_suburbs(
        self,
        suburbs: list[str],
        max_pages_per_suburb: int = 3,
        fetch_details: bool = True
    ) -> list[SoldProperty]:
        """
        Scrape sold property listings from multiple suburbs.

        Args:
            suburbs: List of suburb names
            max_pages_per_suburb: Maximum pages to scrape per suburb
            fetch_details: Whether to fetch land size from individual property pages

        Returns:
            List of all SoldProperty objects from all suburbs
        """
        all_properties = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            for i, suburb in enumerate(suburbs):
                suburb_key = suburb.lower().replace(" ", "-")
                postcode = self.BRISBANE_SUBURBS.get(suburb_key)

                if not postcode:
                    print(f"\n[{i+1}/{len(suburbs)}] Skipping unknown suburb: {suburb}")
                    continue

                print(f"\n{'='*60}")
                print(f"[{i+1}/{len(suburbs)}] Scraping {suburb.replace('-', ' ').title()}, QLD {postcode}")
                print(f"{'='*60}")

                suburb_properties = []
                page_num = 1

                while page_num <= max_pages_per_suburb:
                    url = self._build_search_url(suburb_key, postcode, page_num)
                    print(f"  Fetching page {page_num}...")

                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        await asyncio.sleep(3)

                        properties = await self._scrape_listings_from_page(page, suburb_key, postcode)

                        if properties:
                            existing_urls = {p.listing_url for p in suburb_properties}
                            new_properties = [p for p in properties if p.listing_url not in existing_urls]
                            print(f"  Found {len(new_properties)} new matching listings")
                            suburb_properties.extend(new_properties)
                        else:
                            if page_num > 1:
                                break

                        next_link = await page.query_selector('a[rel="next"]')
                        if not next_link:
                            break

                        page_num += 1
                        await self._random_delay()

                    except Exception as e:
                        print(f"  Error: {e}")
                        break

                # Fetch details for properties in this suburb
                if fetch_details and suburb_properties:
                    print(f"  Fetching land size for {len(suburb_properties)} properties...")
                    for j, prop in enumerate(suburb_properties):
                        print(f"    [{j+1}/{len(suburb_properties)}] {prop.address}")
                        await self._fetch_property_details(page, prop)
                        await self._random_delay(0.5)

                all_properties.extend(suburb_properties)
                print(f"  Suburb total: {len(suburb_properties)} properties")

                # Delay between suburbs
                if i < len(suburbs) - 1:
                    await self._random_delay(1.5)

            await browser.close()

        return all_properties

    def save_results(self, properties: list[SoldProperty], filename: str):
        """Save results to a JSON file."""
        data = [asdict(p) for p in properties]
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved {len(properties)} properties to {filename}")

    def save_results_csv(self, properties: list[SoldProperty], filename: str):
        """Save results to a CSV file."""
        import csv

        if not properties:
            print("No properties to save")
            return

        fieldnames = list(asdict(properties[0]).keys())

        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for prop in properties:
                writer.writerow(asdict(prop))

        print(f"Saved {len(properties)} properties to {filename}")


async def main():
    """Run the scraper on multiple Brisbane suburbs."""
    scraper = BrisbanePropertyScraper(min_delay=1.5, max_delay=3.0, headless=True)

    # Select suburbs across Brisbane metro area
    suburbs = [
        # Inner Brisbane
        "paddington",
        "new-farm",
        "west-end",
        "ashgrove",
        "bardon",
        # Northern
        "chermside",
        "aspley",
        "kedron",
        "albany-creek",
        # Southern
        "mount-gravatt",
        "coorparoo",
        "camp-hill",
        "tarragindi",
        # Western
        "indooroopilly",
        "kenmore",
        "the-gap",
        # Eastern
        "wynnum",
        "carindale",
        "bulimba",
        # Moreton Bay
        "north-lakes",
        "redcliffe",
        # Logan/Gold Coast corridor
        "springwood",
        "helensvale",
        "robina",
    ]

    print(f"\n{'='*60}")
    print(f"Brisbane Property Scraper")
    print(f"Scraping {len(suburbs)} suburbs")
    print(f"Filters: 3-4 bedrooms, Houses only, last 3 months")
    print(f"{'='*60}")

    all_properties = await scraper.scrape_multiple_suburbs(
        suburbs,
        max_pages_per_suburb=2,
        fetch_details=True
    )

    print(f"\n{'='*60}")
    print(f"TOTAL RESULTS: {len(all_properties)} properties")
    print(f"{'='*60}\n")

    # Summary by suburb
    suburb_counts = {}
    for prop in all_properties:
        suburb_counts[prop.suburb] = suburb_counts.get(prop.suburb, 0) + 1

    print("Properties by suburb:")
    for suburb, count in sorted(suburb_counts.items()):
        print(f"  {suburb}: {count}")

    # Properties with prices
    with_prices = [p for p in all_properties if p.sale_price]
    print(f"\nWith disclosed prices: {len(with_prices)}")
    if with_prices:
        prices = [p.sale_price for p in with_prices]
        print(f"  Min: ${min(prices):,}")
        print(f"  Max: ${max(prices):,}")
        print(f"  Avg: ${sum(prices)//len(prices):,}")

    # Properties with land size
    with_land = [p for p in all_properties if p.land_size_sqm]
    print(f"\nWith land size data: {len(with_land)}")
    if with_land:
        sizes = [p.land_size_sqm for p in with_land]
        print(f"  Min: {min(sizes)} sqm")
        print(f"  Max: {max(sizes)} sqm")
        print(f"  Avg: {sum(sizes)//len(sizes)} sqm")

    # Save results
    if all_properties:
        scraper.save_results(all_properties, "brisbane_sold_properties.json")
        scraper.save_results_csv(all_properties, "brisbane_sold_properties.csv")


if __name__ == "__main__":
    asyncio.run(main())
