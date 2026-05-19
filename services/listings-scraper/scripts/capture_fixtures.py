"""Capture OTH search-API fixtures for the parser test suite.

This is a developer one-off, not a runtime component. It uses **bare
Playwright** (NOT camoufox — camoufox is the issue 10 deliverable) to:

1. Open https://www.onthehouse.com.au/ once so cookies/anti-bot tokens settle
   on the page context.
2. For each of the 3 search categories (OTH names them `SaleListing`,
   `RentalListing`, `RecentlySold` — our internal `forsale|forrent|recentlysold`),
   issue a search request via `page.evaluate(fetch(...))` so the call
   inherits the page's session.
3. Save the raw JSON response to
   `services/oth-scraper/tests/fixtures/oth/{category}_{suburb}_p0.json`,
   where `{category}` uses our internal lowercase name.

Default capture is Paddington QLD 4064, a suburb known to have listings in
all three categories. Pass `--suburb` to capture an extra suburb (e.g.
`--suburb "Bondi:NSW:2026"`) when fixtures need more variety (e.g. an
apartment without land size, multiple agents).

Usage
-----

```
# from services/oth-scraper/
uv run playwright install chromium    # one-time, if not already installed
uv run python scripts/capture_fixtures.py
uv run python scripts/capture_fixtures.py --suburb "Bondi:NSW:2026"
```

The script is committed to the repo but **not run in CI**. Re-run only when
OTH's response shape changes and the fixtures need refreshing.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import async_playwright

from listings_scraper.oth_client import Category, ListingFilters, ResolvedSuburb
from listings_scraper.oth_client.payload import SEARCH_URL, build_search_payload

OTH_HOME = "https://www.onthehouse.com.au/"

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "oth"

CATEGORIES = (Category.FORSALE, Category.FORRENT, Category.RECENTLYSOLD)


@dataclass(frozen=True)
class SuburbSpec:
    name: str
    state: str
    postcode: str

    @property
    def slug(self) -> str:
        # filename-safe lowercased suburb token, e.g. "paddington" or "wynnum-west"
        return self.name.lower().replace(" ", "-")

    def to_resolved(self) -> ResolvedSuburb:
        return ResolvedSuburb(name=self.name, state=self.state, postcode=self.postcode)


def parse_suburb_arg(raw: str) -> SuburbSpec:
    parts = raw.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f'expected "Name:STATE:postcode", got {raw!r}'
        )
    name, state, postcode = parts
    return SuburbSpec(name=name.strip(), state=state.strip().upper(), postcode=postcode.strip())


# JS executed inside the page context so the fetch inherits cookies/origin.
FETCH_JS = """
async ({url, payload}) => {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'accept': 'application/json',
            'content-type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    const text = await response.text();
    return { status: response.status, body: text };
}
"""


async def capture_one(page, suburb: SuburbSpec, category: Category) -> dict:
    # Use the production payload builder so fixtures are guaranteed to match
    # what the OTHApiClient will actually send at runtime.
    payload = build_search_payload(
        suburb.to_resolved(), category, ListingFilters(), page=0
    )
    result = await page.evaluate(FETCH_JS, {"url": SEARCH_URL, "payload": payload})
    if result["status"] != 200:
        raise RuntimeError(
            f"OTH returned HTTP {result['status']} for {category.value} {suburb.name}: "
            f"{result['body'][:200]}"
        )
    return json.loads(result["body"])


def fixture_path(suburb: SuburbSpec, category: Category) -> Path:
    return FIXTURES_DIR / f"{category.value}_{suburb.slug}_p0.json"


async def capture_suburb(suburb: SuburbSpec) -> list[Path]:
    written: list[Path] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="en-AU",
            )
            page = await context.new_page()

            print(f"[{suburb.name}] loading {OTH_HOME} ...")
            await page.goto(OTH_HOME, wait_until="domcontentloaded", timeout=30_000)
            # Settle: let any cookie banners / anti-bot challenges run.
            await page.wait_for_timeout(2_500)

            for category in CATEGORIES:
                print(f"[{suburb.name}] fetching {category.value} ({category.oth_name}) ...")
                data = await capture_one(page, suburb, category)
                out = fixture_path(suburb, category)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                count = len(data.get("content", []))
                print(f"  -> {out.relative_to(Path.cwd())} ({count} listings)")
                written.append(out)
                await page.wait_for_timeout(2_000)
        finally:
            await browser.close()
    return written


async def main() -> int:
    parser = argparse.ArgumentParser(description="Capture OTH parser fixtures.")
    parser.add_argument(
        "--suburb",
        type=parse_suburb_arg,
        action="append",
        default=None,
        help=(
            'Suburb spec "Name:STATE:postcode". May be passed multiple times. '
            'Defaults to Paddington QLD 4064.'
        ),
    )
    args = parser.parse_args()

    suburbs: list[SuburbSpec] = args.suburb or [
        SuburbSpec(name="Paddington", state="QLD", postcode="4064")
    ]

    all_written: list[Path] = []
    for suburb in suburbs:
        written = await capture_suburb(suburb)
        all_written.extend(written)

    print()
    print("Captured fixtures:")
    for p in all_written:
        print(f"  {p}")
    print()
    print("Eyeball check before committing:")
    print("  - At least one listing has land_size_sqm")
    print("  - At least one listing is missing land_size_sqm (e.g. an apartment)")
    print("  - ForRent fixture shows a weekly-rent value")
    print("  - At least one listing has missing lat/lon")
    print("If gaps remain, capture another suburb e.g.")
    print('  uv run python scripts/capture_fixtures.py --suburb "Bondi:NSW:2026"')
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
