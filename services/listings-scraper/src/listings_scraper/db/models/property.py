"""SQLAlchemy ORM model for the property table.

A `property` is a physical address. Multiple `listing` rows (marketing
campaigns) can attach to one property over time — the same house being
relisted is a new Listing pointed at the same Property.

Identification:
- Primary natural key: `(source, external_property_id)` partial unique index
  WHERE external_property_id IS NOT NULL.
- Fallback: `(source, formatted_address, postcode)` UNIQUE.
"""
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from listings_scraper.db.engine import Base
from listings_scraper.vendor import Vendor

_vendor_enum = Enum("oth", "domain", name="vendor", create_type=False)


class Property(Base):
    __tablename__ = "property"
    __table_args__ = (
        # Partial unique index: (source, external_property_id) WHERE NOT NULL.
        # Named as a "unique constraint" here; Alembic creates the index.
        Index(
            "uq_property_source_external_property_id",
            "source",
            "external_property_id",
            unique=True,
            postgresql_where=text("external_property_id IS NOT NULL"),
        ),
        UniqueConstraint(
            "source", "formatted_address", "postcode",
            name="uq_property_source_address_postcode",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    external_property_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    formatted_address: Mapped[str] = mapped_column(Text, nullable=False)
    postcode: Mapped[str] = mapped_column(Text, nullable=False)

    # FK to suburb.id — suburb table lives in the issue 02 migration.
    suburb_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("suburb.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # PostGIS Point in WGS84 (EPSG:4326). Nullable: OTH does not always
    # return lat/lon (notably for older recently-sold listings).
    location: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326),
        nullable=True,
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[Vendor] = mapped_column(
        _vendor_enum, nullable=False, default=Vendor.OTH
    )
