"""SQLAlchemy ORM model for the listing table.

A `listing` is one marketing campaign for a property — it has a category
(`forsale`/`forrent`/`recentlysold`), an OTH listing ID, and lifecycle
timestamps. The same physical property can have multiple Listings over time.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from oth_scraper.db.engine import Base

LISTING_CATEGORY_VALUES = ("forsale", "forrent", "recentlysold")
"""Valid values for listing.category. Mirrors oth_client.types.Category."""

CLOSURE_REASON_VALUES = ("unknown", "sold", "withdrawn", "expired")
"""Valid values for listing.closure_reason. NULL = listing still open."""

listing_category_enum = Enum(
    *LISTING_CATEGORY_VALUES,
    name="listing_category",
    native_enum=True,
    create_type=True,
)

closure_reason_enum = Enum(
    *CLOSURE_REASON_VALUES,
    name="listing_closure_reason",
    native_enum=True,
    create_type=True,
)


class Listing(Base):
    __tablename__ = "listing"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    property_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("property.id", ondelete="CASCADE"),
        nullable=False,
    )
    suburb_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("suburb.id", ondelete="RESTRICT"),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(listing_category_enum, nullable=False)

    oth_listing_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    agency_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closure_reason: Mapped[str | None] = mapped_column(closure_reason_enum, nullable=True)

    __table_args__ = (
        # The reconciler's hot lookup: open listing for a (property, suburb, category).
        Index(
            "ix_listing_property_suburb_category_open",
            "property_id",
            "suburb_id",
            "category",
            postgresql_where=text("closed_at IS NULL"),
        ),
        Index("ix_listing_suburb_category", "suburb_id", "category"),
        Index("ix_listing_last_seen_at", "last_seen_at"),
    )
