"""Domain suburb resolver — maps suburb names to Domain URL slugs.

Re-exports:
- `DomainSuburbResolver`: satisfies VendorSuburbResolver protocol
- `SuburbResolutionError`: raised when postcode/state are missing
"""

from listings_scraper.vendor_resolvers.domain.resolver import (
    DomainSuburbResolver,
    SuburbResolutionError,
)

__all__ = ["DomainSuburbResolver", "SuburbResolutionError"]
