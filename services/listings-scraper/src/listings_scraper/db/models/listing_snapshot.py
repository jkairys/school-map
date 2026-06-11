"""SQLAlchemy ORM model for the listing_snapshot table.

Insert-only history of listing observations. The reconciler appends a row
whenever the snapshot diff engine reports a material change.

Invariants:
- `raw_payload` is write-once. Reconciler never updates an existing row.
- `changed_fields` records which material fields differed from the prior
  snapshot. For the first snapshot of a listing the list begins with the
  `__initial__` sentinel from `listings_scraper.snapshot_diff`.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from listings_scraper.db.engine import Base
from listings_scraper.vendor_clients.base import PriceKind

_price_kind_enum = Enum(
    "price", "range", "auction", "eoi", "contact", "rent_weekly", "unknown",
    name="price_kind",
    create_type=False,
)


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    listing_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("listing.id", ondelete="CASCADE"),
        nullable=False,
    )

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_display: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_high: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_kind: Mapped[PriceKind] = mapped_column(
        _price_kind_enum,
        nullable=False,
        default=PriceKind.UNKNOWN,
        server_default="unknown",
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    blurb: Mapped[str | None] = mapped_column(Text, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parking: Mapped[int | None] = mapped_column(Integer, nullable=True)
    land_size_sqm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    property_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_listing_snapshot_listing_id_observed_at",
            "listing_id",
            "observed_at",
        ),
    )
