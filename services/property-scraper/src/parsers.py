"""Parsing functions for property data."""

import re
from datetime import datetime, timedelta
from typing import Optional


def parse_price(price_str: Optional[str]) -> Optional[int]:
    """Parse a price string into an integer.

    Args:
        price_str: Price string like "$750,000" or "not available"

    Returns:
        Integer price or None if not parseable
    """
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


def parse_sold_date(text: str) -> Optional[str]:
    """Extract sold date from ribbon text like 'Sold on 23 Dec 2025'.

    Args:
        text: Text containing sold date

    Returns:
        Formatted date string or None
    """
    match = re.search(r'Sold\s+(?:on\s+)?(\d{1,2}\s+\w+\s+\d{4})', text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def parse_land_size(text: str) -> Optional[int]:
    """Extract land size in sqm from text.

    Args:
        text: Text containing land size like "650 m²" or "650m2"

    Returns:
        Land size in square meters or None
    """
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


def is_within_date_range(date_str: Optional[str], days: int = 90) -> bool:
    """Check if a date string is within the specified number of days.

    Args:
        date_str: Date string in various formats
        days: Number of days to check against (default: 90)

    Returns:
        True if within range, True if date unparseable (benefit of doubt)
    """
    if not date_str:
        return True

    cutoff_date = datetime.now() - timedelta(days=days)

    date_formats = [
        "%d %b %Y",
        "%d %B %Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]

    for fmt in date_formats:
        try:
            sale_date = datetime.strptime(date_str.strip(), fmt)
            return sale_date >= cutoff_date
        except ValueError:
            continue

    return True
