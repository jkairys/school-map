"""scrape_run table + scrape_job.run_id

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-11 00:00:00.000000

Adds the first-class ``scrape_run`` entity and links every ``scrape_job``
back to it via a NOT NULL ``run_id`` FK.

Dev data is dropped (no backfill required per PRD).  The downgrade wipes
``scrape_job`` rows before removing the column and table so FK constraints
are never violated on rollback.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RUN_STATUS_VALUES = ("running", "succeeded", "partial", "failed")
RUN_TRIGGER_SOURCE_VALUES = ("api", "cli", "scheduler", "retry")


def upgrade() -> None:
    run_status = postgresql.ENUM(*RUN_STATUS_VALUES, name="scrape_run_status")
    run_trigger_source = postgresql.ENUM(
        *RUN_TRIGGER_SOURCE_VALUES, name="scrape_run_trigger_source"
    )

    # ------------------------------------------------------------------ #
    # 1. Create scrape_run table                                           #
    # ------------------------------------------------------------------ #
    op.create_table(
        "scrape_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "scrape_list_id",
            sa.BigInteger(),
            sa.ForeignKey("scrape_list.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            run_status,
            nullable=False,
            server_default="running",
        ),
        sa.Column(
            "trigger_source",
            run_trigger_source,
            nullable=False,
        ),
        sa.Column(
            "filters_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "retried_from_run_id",
            sa.BigInteger(),
            sa.ForeignKey("scrape_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------ #
    # 2. Add run_id to scrape_job                                          #
    #                                                                      #
    # Dev data is dropped — no backfill needed.  We truncate first so the  #
    # NOT NULL constraint can be added without a default.                   #
    # ------------------------------------------------------------------ #
    op.execute("TRUNCATE TABLE scrape_job RESTART IDENTITY CASCADE")

    op.add_column(
        "scrape_job",
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("scrape_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_scrape_job_run_id",
        "scrape_job",
        ["run_id"],
    )


def downgrade() -> None:
    # Remove index and column first, then the table.
    op.drop_index("ix_scrape_job_run_id", table_name="scrape_job")
    op.execute("TRUNCATE TABLE scrape_job RESTART IDENTITY CASCADE")
    op.drop_column("scrape_job", "run_id")

    op.drop_table("scrape_run")

    postgresql.ENUM(*RUN_TRIGGER_SOURCE_VALUES, name="scrape_run_trigger_source").drop(
        op.get_bind(), checkfirst=True
    )
    postgresql.ENUM(*RUN_STATUS_VALUES, name="scrape_run_status").drop(
        op.get_bind(), checkfirst=True
    )
