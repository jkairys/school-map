"""Vendor enum — identifies which real-estate portal a listing comes from.

Used as a discriminator on all DB tables (`source` column) and on
`VendorListing` so parsers and reconcilers can branch on source without
importing each other's implementations.
"""

from enum import Enum


class Vendor(str, Enum):
    OTH = "oth"
    DOMAIN = "domain"
