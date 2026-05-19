"""scrape_job queue table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-07 00:00:01.000000

The suburb_id and scrape_list_id columns are intentionally created WITHOUT
foreign-key constraints in this migration. The suburb table lands in issue 02
and the scrape_list table lands in issue 03; once both exist a follow-up
migration will add the physical FK constraints. Until then both columns are
plain nullable BigInteger references.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JOB_STATUS_VALUES = ("queued", "running", "succeeded", "failed", "deadletter")


def upgrade() -> None:
    # Single ENUM instance — create_table will emit CREATE TYPE once before
    # CREATE TABLE. Using two separate Enum() instances would double-emit.
    status_enum = postgresql.ENUM(
        *JOB_STATUS_VALUES, name="scrape_job_status"
    )

    op.create_table(
        "scrape_job",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # NOTE: scrape_list_id and suburb_id are nullable BigInteger refs WITHOUT
        # physical FK constraints — see migration docstring above.
        sa.Column("scrape_list_id", sa.BigInteger(), nullable=True),
        sa.Column("suburb_id", sa.BigInteger(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            status_enum,
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_error_class", sa.String(length=32), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        comment=(
            "Postgres-backed scrape queue. suburb_id and scrape_list_id are "
            "intentionally not FK-constrained in this migration; a later "
            "migration adds constraints once issues 02/03 land."
        ),
    )
    op.create_index(
        "ix_scrape_job_status_created_at",
        "scrape_job",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_scrape_job_claimed_at",
        "scrape_job",
        ["claimed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_scrape_job_claimed_at", table_name="scrape_job")
    op.drop_index("ix_scrape_job_status_created_at", table_name="scrape_job")
    op.drop_table("scrape_job")
    postgresql.ENUM(
        *JOB_STATUS_VALUES, name="scrape_job_status"
    ).drop(op.get_bind(), checkfirst=True)
