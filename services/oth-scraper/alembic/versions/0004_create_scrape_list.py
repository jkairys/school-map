"""create scrape_list and scrape_list_suburb tables; add deferred FKs on scrape_job

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-07 00:00:02.000000

Issue 04 (0002_scrape_job) created scrape_job with nullable scrape_list_id and
suburb_id columns intentionally without FK constraints, because the target
tables landed in later issues. Now that suburb (0003) and scrape_list (this
migration) both exist, this migration both creates scrape_list / m2m and
attaches the previously-deferred FK constraints to scrape_job.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scrape_list",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("cron_schedule", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "scrape_list_suburb",
        sa.Column("scrape_list_id", sa.BigInteger(), nullable=False),
        sa.Column("suburb_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "scrape_list_id", "suburb_id", name="pk_scrape_list_suburb"
        ),
        sa.ForeignKeyConstraint(
            ["scrape_list_id"],
            ["scrape_list.id"],
            name="fk_scrape_list_suburb_list",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["suburb_id"],
            ["suburb.id"],
            name="fk_scrape_list_suburb_suburb",
            ondelete="RESTRICT",
        ),
    )

    # Attach the FK constraints that 0002_scrape_job intentionally deferred.
    op.create_foreign_key(
        "fk_scrape_job_scrape_list",
        source_table="scrape_job",
        referent_table="scrape_list",
        local_cols=["scrape_list_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_scrape_job_suburb",
        source_table="scrape_job",
        referent_table="suburb",
        local_cols=["suburb_id"],
        remote_cols=["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_scrape_job_suburb", "scrape_job", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_scrape_job_scrape_list", "scrape_job", type_="foreignkey"
    )
    op.drop_table("scrape_list_suburb")
    op.drop_table("scrape_list")
