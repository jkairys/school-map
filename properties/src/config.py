"""Configuration and constants for the Brisbane Property Scraper."""

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
    """Load suburb data from JSON file.

    Returns:
        Dictionary mapping suburb names to postcodes
    """
    with open(SUBURBS_FILE) as f:
        return json.load(f)
