"""SQLAlchemy ORM model for the property table.

A `property` is a physical address. Multiple `listing` rows (marketing
campaigns) can attach to one property over time — the same house being
relisted is a new Listing pointed at the same Property.

Identification:
- Primary natural key: `oth_property_id` (UNIQUE, nullable for safety on
  pre-OTH inserts; reconciler always populates it).
- Fallback: `(formatted_address, postcode)` UNIQUE.
"""
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from oth_scraper.db.engine import Base


class Property(Base):
    __tablename__ = "property"
    __table_args__ = (
        UniqueConstraint("oth_property_id", name="uq_property_oth_property_id"),
        UniqueConstraint(
            "formatted_address", "postcode", name="uq_property_address_postcode"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    oth_property_id: Mapped[str | None] = mapped_column(Text, nullable=True)
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
