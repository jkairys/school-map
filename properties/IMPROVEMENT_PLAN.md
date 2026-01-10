# Brisbane Property Scraper - Improvement Plan

## Current State Analysis

The existing scraper is a single 807-line Python file with the following characteristics:

| Aspect | Current State | Issues |
|--------|--------------|--------|
| **File structure** | Monolithic single file | Hard to maintain, test, and understand |
| **JavaScript** | Two large embedded JS blocks (~120 lines total) | Mixed languages, hard to debug |
| **Suburb data** | Hardcoded dictionary (~160 entries) | Bloats main file, hard to update |
| **Data storage** | Same directory as code | Mixes concerns, messy repository |
| **Concurrency** | Not supported | Cannot run parallel instances |
| **Progress saving** | Only at end | Lost work on failures |

---

## Proposed Architecture

```
properties/
├── src/
│   ├── __init__.py
│   ├── scraper.py           # Core BrisbanePropertyScraper class
│   ├── models.py            # SoldProperty dataclass
│   ├── parsers.py           # Price, date, land size parsing functions
│   ├── storage.py           # File I/O with locking support
│   └── config.py            # Configuration and constants
├── js/
│   ├── extract_listings.js  # Page scraping logic
│   └── extract_details.js   # Property detail extraction
├── data/
│   ├── suburbs.json         # Suburb definitions
│   ├── output/              # Scraped data output
│   │   ├── paddington.json
│   │   ├── new-farm.json
│   │   └── ...
│   └── combined/            # Merged output files
│       └── brisbane_sold_properties.json
├── run_scraper.py           # CLI entry point
├── requirements.txt
└── IMPROVEMENT_PLAN.md
```

---

## Phase 1: Modularize Python Codebase

### 1.1 Create `src/models.py`
Extract the `SoldProperty` dataclass.

```python
# src/models.py
from dataclasses import dataclass, asdict, field
from typing import Optional

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

    def to_dict(self) -> dict:
        return asdict(self)
```

### 1.2 Create `src/parsers.py`
Extract all parsing functions.

```python
# src/parsers.py
import re
from datetime import datetime, timedelta
from typing import Optional

def parse_price(price_str: Optional[str]) -> Optional[int]:
    """Parse a price string into an integer."""
    ...

def parse_sold_date(text: str) -> Optional[str]:
    """Extract sold date from ribbon text like 'Sold on 23 Dec 2025'."""
    ...

def parse_land_size(text: str) -> Optional[int]:
    """Extract land size in sqm from text."""
    ...

def is_within_date_range(date_str: Optional[str], days: int = 90) -> bool:
    """Check if a date string is within the specified number of days."""
    ...
```

### 1.3 Create `src/config.py`
Centralize configuration and load suburb data.

```python
# src/config.py
import json
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "output"
COMBINED_DIR = DATA_DIR / "combined"
JS_DIR = PROJECT_ROOT / "js"
SUBURBS_FILE = DATA_DIR / "suburbs.json"

# Scraper settings
DEFAULT_MIN_DELAY = 1.5
DEFAULT_MAX_DELAY = 3.0
DEFAULT_MAX_PAGES = 5
BASE_URL = "https://www.onthehouse.com.au"

# Ensure directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
COMBINED_DIR.mkdir(parents=True, exist_ok=True)

def load_suburbs() -> dict[str, str]:
    """Load suburb data from JSON file."""
    with open(SUBURBS_FILE) as f:
        return json.load(f)
```

### 1.4 Create `src/storage.py`
Handle file I/O with locking for concurrent access.

```python
# src/storage.py
import json
import csv
import fcntl
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import SoldProperty

class SuburbStorage:
    """Handles per-suburb data storage with file locking."""

    def __init__(self, suburb: str, output_dir: Path):
        self.suburb = suburb
        self.output_dir = output_dir
        self.filename = output_dir / f"{suburb}.json"

    def load_existing(self) -> list[dict]:
        """Load existing scraped data for this suburb."""
        if not self.filename.exists():
            return []
        with open(self.filename) as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def save(self, properties: list["SoldProperty"]):
        """Save properties to suburb-specific file with exclusive lock."""
        with open(self.filename, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump([p.to_dict() for p in properties], f, indent=2)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def append(self, properties: list["SoldProperty"]):
        """Append new properties, avoiding duplicates."""
        existing = self.load_existing()
        existing_urls = {p["listing_url"] for p in existing}

        new_props = [p.to_dict() for p in properties
                     if p.listing_url not in existing_urls]

        if new_props:
            with open(self.filename, "w") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(existing + new_props, f, indent=2)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        return len(new_props)


def combine_suburb_files(output_dir: Path, combined_file: Path):
    """Merge all suburb JSON files into one combined file."""
    all_properties = []
    seen_urls = set()

    for suburb_file in output_dir.glob("*.json"):
        with open(suburb_file) as f:
            for prop in json.load(f):
                if prop["listing_url"] not in seen_urls:
                    seen_urls.add(prop["listing_url"])
                    all_properties.append(prop)

    with open(combined_file, "w") as f:
        json.dump(all_properties, f, indent=2)

    return len(all_properties)
```

### 1.5 Create `src/scraper.py`
Core scraper class, now importing from other modules.

```python
# src/scraper.py
import asyncio
import random
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser

from .config import (
    BASE_URL, DEFAULT_MIN_DELAY, DEFAULT_MAX_DELAY,
    JS_DIR, load_suburbs
)
from .models import SoldProperty
from .parsers import parse_price, parse_sold_date, is_within_date_range
from .storage import SuburbStorage

class BrisbanePropertyScraper:
    """Scraper for sold property data from onthehouse.com.au."""

    def __init__(
        self,
        min_delay: float = DEFAULT_MIN_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        headless: bool = True
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.headless = headless
        self.suburbs = load_suburbs()

        # Load JavaScript files
        self._listings_js = (JS_DIR / "extract_listings.js").read_text()
        self._details_js = (JS_DIR / "extract_details.js").read_text()

    async def scrape_suburb(
        self,
        suburb: str,
        storage: SuburbStorage,
        max_pages: int = 5,
        fetch_details: bool = True,
        save_incrementally: bool = True
    ) -> list[SoldProperty]:
        """Scrape a single suburb with incremental saving."""
        ...
```

---

## Phase 2: Extract JavaScript Files

### 2.1 Create `js/extract_listings.js`
Extract the page scraping logic (currently lines 385-463).

```javascript
// js/extract_listings.js
(() => {
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

            // ... (rest of extraction logic)

            if (listing.address || listing.url) {
                listings.push(listing);
            }
        } catch (e) {
            console.error('Error parsing card ' + index + ': ' + e);
        }
    });

    return listings;
})();
```

### 2.2 Create `js/extract_details.js`
Extract the property detail extraction (currently lines 295-355).

```javascript
// js/extract_details.js
(() => {
    const result = {
        landSize: null,
        description: '',
        beds: null,
        baths: null,
        parking: null
    };

    // ... (rest of detail extraction logic)

    return result;
})();
```

---

## Phase 3: Implement CLI with Single-Suburb Mode

### 3.1 Create `run_scraper.py`
New entry point with CLI argument parsing.

```python
#!/usr/bin/env python3
"""CLI entry point for the Brisbane Property Scraper."""

import argparse
import asyncio
import sys
from pathlib import Path

from src.config import OUTPUT_DIR, COMBINED_DIR, load_suburbs
from src.scraper import BrisbanePropertyScraper
from src.storage import SuburbStorage, combine_suburb_files


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scrape Brisbane property sold data"
    )

    # Mode selection
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--suburb", "-s",
        help="Scrape a single suburb (e.g., 'paddington' or 'st-lucia')"
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Scrape all suburbs in the suburbs.json file"
    )
    mode.add_argument(
        "--list-suburbs",
        action="store_true",
        help="List all available suburbs"
    )
    mode.add_argument(
        "--combine",
        action="store_true",
        help="Combine all suburb files into one"
    )

    # Options
    parser.add_argument(
        "--max-pages", "-p",
        type=int,
        default=5,
        help="Maximum pages to scrape per suburb (default: 5)"
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Skip fetching individual property details"
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run browser in visible mode (not headless)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Output directory (default: {OUTPUT_DIR})"
    )

    return parser.parse_args()


async def scrape_single_suburb(args):
    """Scrape a single suburb."""
    scraper = BrisbanePropertyScraper(headless=not args.visible)
    storage = SuburbStorage(args.suburb, args.output_dir)

    properties = await scraper.scrape_suburb(
        suburb=args.suburb,
        storage=storage,
        max_pages=args.max_pages,
        fetch_details=not args.no_details,
        save_incrementally=True
    )

    print(f"\nCompleted: {len(properties)} properties saved to {storage.filename}")


async def scrape_all_suburbs(args):
    """Scrape all suburbs sequentially."""
    suburbs = load_suburbs()
    scraper = BrisbanePropertyScraper(headless=not args.visible)

    for i, suburb in enumerate(suburbs.keys()):
        print(f"\n[{i+1}/{len(suburbs)}] {suburb}")
        storage = SuburbStorage(suburb, args.output_dir)

        await scraper.scrape_suburb(
            suburb=suburb,
            storage=storage,
            max_pages=args.max_pages,
            fetch_details=not args.no_details,
            save_incrementally=True
        )


def main():
    args = parse_args()

    if args.list_suburbs:
        suburbs = load_suburbs()
        print(f"Available suburbs ({len(suburbs)}):")
        for suburb, postcode in sorted(suburbs.items()):
            print(f"  {suburb}: {postcode}")
        return

    if args.combine:
        count = combine_suburb_files(
            args.output_dir,
            COMBINED_DIR / "brisbane_sold_properties.json"
        )
        print(f"Combined {count} properties")
        return

    if args.suburb:
        asyncio.run(scrape_single_suburb(args))
    elif args.all:
        asyncio.run(scrape_all_suburbs(args))


if __name__ == "__main__":
    main()
```

---

## Phase 4: Concurrent Instance Support

### Design Decisions

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Single combined file with locking** | Simple | Lock contention, corruption risk | ❌ Rejected |
| **Per-suburb files** | No contention, easy to merge | More files | ✅ Chosen |
| **Database (SQLite)** | ACID, queries | Overkill, added dependency | ❌ Rejected |

### Implementation

1. **Each suburb writes to its own file**: `data/output/{suburb}.json`
2. **File locking on write**: Using `fcntl.flock()` for safety
3. **Combine operation**: Separate command to merge all suburb files
4. **Lock file for coordination**: Optional `.lock` file to prevent same suburb being scraped twice

### Usage Examples

```bash
# Terminal 1 - Scrape northern suburbs
python run_scraper.py --suburb paddington
python run_scraper.py --suburb new-farm
python run_scraper.py --suburb ashgrove

# Terminal 2 - Scrape southern suburbs (simultaneously)
python run_scraper.py --suburb coorparoo
python run_scraper.py --suburb camp-hill
python run_scraper.py --suburb tarragindi

# After all complete, combine results
python run_scraper.py --combine
```

---

## Phase 5: Data Directory Structure

### 5.1 Create `data/suburbs.json`
Move suburb definitions out of code.

```json
{
  "paddington": "4064",
  "red-hill": "4059",
  "kelvin-grove": "4059",
  "new-farm": "4005",
  ...
}
```

### 5.2 Directory Layout
```
data/
├── suburbs.json              # Suburb definitions
├── output/                   # Per-suburb scraped data
│   ├── paddington.json
│   ├── new-farm.json
│   └── ...
└── combined/                 # Merged outputs
    ├── brisbane_sold_properties.json
    └── brisbane_sold_properties.csv
```

### 5.3 Add to `.gitignore`
```gitignore
# Scraped data (regeneratable)
properties/data/output/
properties/data/combined/

# Keep structure
!properties/data/output/.gitkeep
!properties/data/combined/.gitkeep
```

---

## Implementation Order

### Step 1: Create directory structure
- [ ] Create `src/`, `js/`, `data/` directories
- [ ] Create `data/output/`, `data/combined/` with `.gitkeep` files
- [ ] Update `.gitignore`

### Step 2: Extract data files
- [ ] Create `data/suburbs.json` from the hardcoded dictionary
- [ ] Create `js/extract_listings.js`
- [ ] Create `js/extract_details.js`

### Step 3: Create Python modules
- [ ] Create `src/__init__.py`
- [ ] Create `src/models.py`
- [ ] Create `src/parsers.py`
- [ ] Create `src/config.py`
- [ ] Create `src/storage.py`
- [ ] Create `src/scraper.py`

### Step 4: Create CLI entry point
- [ ] Create `run_scraper.py` with argparse
- [ ] Add single-suburb mode
- [ ] Add combine mode
- [ ] Add list-suburbs mode

### Step 5: Update and test
- [ ] Create `requirements.txt`
- [ ] Test single suburb scraping
- [ ] Test concurrent instances
- [ ] Test combine operation

### Step 6: Cleanup
- [ ] Remove or archive original `brisbane_property_scraper.py`
- [ ] Update any documentation

---

## Testing Concurrent Instances

### Test Script
```bash
#!/bin/bash
# test_concurrent.sh

# Start multiple scrapers in parallel
python run_scraper.py --suburb paddington &
python run_scraper.py --suburb new-farm &
python run_scraper.py --suburb ashgrove &

# Wait for all to complete
wait

# Combine results
python run_scraper.py --combine

# Check output
echo "Results:"
ls -la data/output/
cat data/combined/brisbane_sold_properties.json | python -m json.tool | head -50
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| File corruption during concurrent write | Per-suburb files eliminate contention |
| Lost progress on crash | Incremental saving after each page/property |
| Rate limiting | Existing random delays, plus configurable |
| JavaScript selector changes | Selectors isolated in `.js` files for easy updates |
| Missing suburb in lookup | Graceful error handling, continue with others |

---

## Future Enhancements (Out of Scope)

These are noted but **not part of this plan**:

1. **Resume capability**: Track progress in a state file to resume interrupted scrapes
2. **Proxy rotation**: Support for rotating proxies to avoid IP bans
3. **Scheduling**: Cron-friendly mode for regular updates
4. **Database storage**: SQLite or PostgreSQL for complex queries
5. **API endpoint**: REST API wrapper for integration
6. **Notifications**: Slack/email alerts on completion or errors
