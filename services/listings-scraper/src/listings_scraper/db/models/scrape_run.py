"""SQLAlchemy ORM model for the scrape_run table.

A scrape_run is the first-class record of a triggered run — one row per
invocation (API, CLI, scheduler, or retry).  Every scrape_job that belongs
to the run links back via ``run_id``.

Status transitions are driven by ``ScrapeRunFinalizer.recompute(run_id)``
which is called at the end of every terminal job transition.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from listings_scraper.db.engine import Base

RUN_STATUS_VALUES = ("running", "succeeded", "partial", "failed")
"""Valid values for scrape_run.status."""

RUN_TRIGGER_SOURCE_VALUES = ("api", "cli", "scheduler", "retry")
"""Valid values for scrape_run.trigger_source."""

run_status_enum = Enum(
    *RUN_STATUS_VALUES,
    name="scrape_run_status",
    native_enum=True,
    create_type=True,
)

run_trigger_source_enum = Enum(
    *RUN_TRIGGER_SOURCE_VALUES,
    name="scrape_run_trigger_source",
    native_enum=True,
    create_type=True,
)


class ScrapeRun(Base):
    __tablename__ = "scrape_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Nullable so ad-hoc runs (not tied to a scrape_list) are possible.
    scrape_list_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("scrape_list.id", ondelete="SET NULL"),
        nullable=True,
    )

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str] = mapped_column(
        run_status_enum, nullable=False, default="running", server_default="running"
    )
    trigger_source: Mapped[str] = mapped_column(
        run_trigger_source_enum, nullable=False
    )

    filters_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    # Self-referential FK for retry lineage.
    retried_from_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("scrape_run.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
