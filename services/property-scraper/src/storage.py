"""Storage module for handling file I/O with locking support."""

import json
import fcntl
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import SoldProperty


class SuburbStorage:
    """Handles per-suburb data storage with file locking."""

    def __init__(self, suburb: str, output_dir: Path):
        """Initialize storage for a specific suburb.

        Args:
            suburb: Suburb name (hyphenated)
            output_dir: Directory where suburb files are stored
        """
        self.suburb = suburb
        self.output_dir = output_dir
        self.filename = output_dir / f"{suburb}.json"

    def load_existing(self) -> list[dict]:
        """Load existing scraped data for this suburb.

        Returns:
            List of property dictionaries
        """
        if not self.filename.exists():
            return []
        with open(self.filename) as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def save(self, properties: list["SoldProperty"]):
        """Save properties to suburb-specific file with exclusive lock.

        Args:
            properties: List of SoldProperty objects to save
        """
        with open(self.filename, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump([p.to_dict() for p in properties], f, indent=2)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def append(self, properties: list["SoldProperty"]) -> int:
        """Append new properties, avoiding duplicates.

        Args:
            properties: List of SoldProperty objects to append

        Returns:
            Number of new properties added
        """
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


def combine_suburb_files(output_dir: Path, combined_file: Path) -> int:
    """Merge all suburb JSON files into one combined file.

    Args:
        output_dir: Directory containing suburb files
        combined_file: Path to output combined file

    Returns:
        Total number of properties in combined file
    """
    all_properties = []
    seen_urls = set()

    for suburb_file in sorted(output_dir.glob("*.json")):
        with open(suburb_file) as f:
            for prop in json.load(f):
                if prop["listing_url"] not in seen_urls:
                    seen_urls.add(prop["listing_url"])
                    all_properties.append(prop)

    with open(combined_file, "w") as f:
        json.dump(all_properties, f, indent=2)

    return len(all_properties)
