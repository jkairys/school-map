"""SQLAlchemy ORM models for scrape_list and scrape_list_suburb m2m."""
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from listings_scraper.db.engine import Base
from listings_scraper.vendor import Vendor

_vendor_enum = Enum("oth", "domain", name="vendor", create_type=False)


class ScrapeList(Base):
    __tablename__ = "scrape_list"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    cron_schedule: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[Vendor] = mapped_column(
        _vendor_enum, nullable=False, default=Vendor.OTH, server_default="oth"
    )


class ScrapeListSuburb(Base):
    __tablename__ = "scrape_list_suburb"
    __table_args__ = (
        PrimaryKeyConstraint(
            "scrape_list_id", "suburb_id", name="pk_scrape_list_suburb"
        ),
    )

    scrape_list_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("scrape_list.id", ondelete="CASCADE"),
        nullable=False,
    )
    suburb_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("suburb.id", ondelete="RESTRICT"),
        nullable=False,
    )
