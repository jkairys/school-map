"""property, listing, listing_snapshot tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-07 00:00:03.000000

Adds the heart of the data model: physical address (`property`) → marketing
campaign (`listing`) → time-series observations (`listing_snapshot`).

PostGIS: relies on the `postgis` extension created in migration 0001. The
`property.location` column is `geography(Point, 4326)`.

Note: this branch was originally authored against 0003 but the parallel
issue 03 migration (`0004_create_scrape_list`) merged first — chaining
0005 on top of 0004 keeps the linear history Alembic expects.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LISTING_CATEGORY_VALUES = ("forsale", "forrent", "recentlysold")
CLOSURE_REASON_VALUES = ("unknown", "sold", "withdrawn", "expired")


def upgrade() -> None:
    listing_category = postgresql.ENUM(
        *LISTING_CATEGORY_VALUES, name="listing_category"
    )
    closure_reason = postgresql.ENUM(
        *CLOSURE_REASON_VALUES, name="listing_closure_reason"
    )

    op.create_table(
        "property",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("oth_property_id", sa.Text(), nullable=True),
        sa.Column("formatted_address", sa.Text(), nullable=False),
        sa.Column("postcode", sa.Text(), nullable=False),
        sa.Column(
            "suburb_id",
            sa.BigInteger(),
            sa.ForeignKey("suburb.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "location",
            Geography(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("oth_property_id", name="uq_property_oth_property_id"),
        sa.UniqueConstraint(
            "formatted_address", "postcode", name="uq_property_address_postcode"
        ),
    )

    op.create_table(
        "listing",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "property_id",
            sa.BigInteger(),
            sa.ForeignKey("property.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "suburb_id",
            sa.BigInteger(),
            sa.ForeignKey("suburb.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("category", listing_category, nullable=False),
        sa.Column("oth_listing_id", sa.Text(), nullable=True),
        sa.Column("agent_name", sa.Text(), nullable=True),
        sa.Column("agency_name", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closure_reason", closure_reason, nullable=True),
    )

    # Partial index so the reconciler's hot lookup (open listing for a
    # (property, suburb, category)) is cheap.
    op.create_index(
        "ix_listing_property_suburb_category_open",
        "listing",
        ["property_id", "suburb_id", "category"],
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_index(
        "ix_listing_suburb_category",
        "listing",
        ["suburb_id", "category"],
    )
    op.create_index(
        "ix_listing_last_seen_at",
        "listing",
        ["last_seen_at"],
    )

    op.create_table(
        "listing_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "listing_id",
            sa.BigInteger(),
            sa.ForeignKey("listing.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("blurb", sa.Text(), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("bathrooms", sa.Integer(), nullable=True),
        sa.Column("parking", sa.Integer(), nullable=True),
        sa.Column("land_size_sqm", sa.Integer(), nullable=True),
        sa.Column("property_type", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "changed_fields",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_listing_snapshot_listing_id_observed_at",
        "listing_snapshot",
        ["listing_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_listing_snapshot_listing_id_observed_at",
        table_name="listing_snapshot",
    )
    op.drop_table("listing_snapshot")

    op.drop_index("ix_listing_last_seen_at", table_name="listing")
    op.drop_index("ix_listing_suburb_category", table_name="listing")
    op.drop_index(
        "ix_listing_property_suburb_category_open",
        table_name="listing",
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.drop_table("listing")

    op.drop_table("property")

    postgresql.ENUM(*CLOSURE_REASON_VALUES, name="listing_closure_reason").drop(
        op.get_bind(), checkfirst=True
    )
    postgresql.ENUM(*LISTING_CATEGORY_VALUES, name="listing_category").drop(
        op.get_bind(), checkfirst=True
    )
