"""SQLAlchemy ORM model for the scrape_job queue table.

The retry policy lives outside this model — see listings_scraper.queue.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from listings_scraper.db.engine import Base
from listings_scraper.vendor import Vendor

JOB_STATUS_VALUES = ("queued", "running", "succeeded", "failed", "deadletter")

_vendor_enum = Enum("oth", "domain", name="vendor", create_type=False)
"""Valid values for scrape_job.status."""

# Reusable Enum type. native_enum=True creates a Postgres ENUM type called
# scrape_job_status. The same type is referenced from the Alembic migration.
job_status_enum = Enum(
    *JOB_STATUS_VALUES,
    name="scrape_job_status",
    native_enum=True,
    create_type=True,
)


class ScrapeJob(Base):
    __tablename__ = "scrape_job"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Nullable FKs without a physical FK constraint (issue 04 lands ahead of the
    # tables they would point to — issue 02 adds suburb, issue 03 adds scrape_list).
    scrape_list_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    suburb_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    category: Mapped[str] = mapped_column(String(32), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    status: Mapped[str] = mapped_column(
        job_status_enum, nullable=False, default="queued", server_default="queued"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[Vendor] = mapped_column(
        _vendor_enum, nullable=False, default=Vendor.OTH, server_default="oth"
    )

    __table_args__ = (
        Index("ix_scrape_job_status_created_at", "status", "created_at"),
        Index("ix_scrape_job_claimed_at", "claimed_at"),
    )
