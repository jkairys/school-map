"""rename oth_* columns to vendor-neutral names; add price representation columns

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-20 00:00:00.000000

Destructive migration — renames OTH-specific columns to vendor-neutral names
and adds price representation columns to listing_snapshot.

Operations (forward):
1. Rename suburb.oth_slug → slug
2. Replace uq_suburb_name_postcode_state with (source, name, postcode, state)
3. Rename property.oth_property_id → external_property_id
4. Replace uq_property_oth_property_id (bare) with partial unique index
   (source, external_property_id) WHERE external_property_id IS NOT NULL
5. Replace uq_property_address_postcode with (source, formatted_address, postcode)
6. Rename listing.oth_listing_id → external_listing_id
7. Add partial unique index (source, external_listing_id)
   WHERE external_listing_id IS NOT NULL
8. Add listing_snapshot.price_display TEXT NULLABLE
9. Add listing_snapshot.price_high INTEGER NULLABLE
10. Add price_kind enum type with values (price, range, auction, eoi, contact,
    rent_weekly, unknown)
11. Add listing_snapshot.price_kind NULLABLE, backfill to 'price' where
    price IS NOT NULL else 'unknown', then set NOT NULL with server_default
12. Drop server_default='oth' from the five source columns added in 0006

Downgrade note: reverses all of the above. Downgrade drops `source='domain'`
rows' uniqueness assumptions — only safe pre-Domain-data. If any
source='domain' rows have been written between forward and reverse migration,
rolling back will leave those rows with constraints that assume a single-vendor
dataset.

Lossless: the only data write is the price_kind backfill, derived from
`price IS NOT NULL`. No rows are deleted.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRICE_KIND_VALUES = ("price", "range", "auction", "eoi", "contact", "rent_weekly", "unknown")

price_kind_enum = sa.Enum(*PRICE_KIND_VALUES, name="price_kind")

_SOURCE_TABLES = ("suburb", "property", "listing", "scrape_job", "scrape_list")


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. suburb: rename oth_slug → slug
    # ------------------------------------------------------------------
    op.alter_column("suburb", "oth_slug", new_column_name="slug")

    # 2. suburb: replace (name, postcode, state) unique with (source, name, postcode, state)
    op.drop_constraint("uq_suburb_name_postcode_state", "suburb", type_="unique")
    op.create_unique_constraint(
        "uq_suburb_source_name_postcode_state",
        "suburb",
        ["source", "name", "postcode", "state"],
    )

    # ------------------------------------------------------------------
    # 3. property: rename oth_property_id → external_property_id
    # ------------------------------------------------------------------
    op.alter_column("property", "oth_property_id", new_column_name="external_property_id")

    # 4. property: drop bare unique on oth_property_id; add partial composite unique
    op.drop_constraint("uq_property_oth_property_id", "property", type_="unique")
    op.create_index(
        "uq_property_source_external_property_id",
        "property",
        ["source", "external_property_id"],
        unique=True,
        postgresql_where=sa.text("external_property_id IS NOT NULL"),
    )

    # 5. property: replace (formatted_address, postcode) unique with
    # (source, formatted_address, postcode)
    op.drop_constraint("uq_property_address_postcode", "property", type_="unique")
    op.create_unique_constraint(
        "uq_property_source_address_postcode",
        "property",
        ["source", "formatted_address", "postcode"],
    )

    # ------------------------------------------------------------------
    # 6. listing: rename oth_listing_id → external_listing_id
    # ------------------------------------------------------------------
    op.alter_column("listing", "oth_listing_id", new_column_name="external_listing_id")

    # 7. listing: add partial unique index on (source, external_listing_id)
    op.create_index(
        "uq_listing_source_external_listing_id",
        "listing",
        ["source", "external_listing_id"],
        unique=True,
        postgresql_where=sa.text("external_listing_id IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # 8-11. listing_snapshot: price_display, price_high, price_kind
    # ------------------------------------------------------------------
    op.add_column(
        "listing_snapshot",
        sa.Column("price_display", sa.Text(), nullable=True),
    )
    op.add_column(
        "listing_snapshot",
        sa.Column("price_high", sa.Integer(), nullable=True),
    )

    # Create the enum type first, then add the column as NULLABLE for backfill.
    price_kind_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "listing_snapshot",
        sa.Column(
            "price_kind",
            sa.Enum(*PRICE_KIND_VALUES, name="price_kind", create_type=False),
            nullable=True,
        ),
    )

    # Backfill: price IS NOT NULL → 'price', else → 'unknown'
    op.execute(
        sa.text(
            "UPDATE listing_snapshot "
            "SET price_kind = CASE WHEN price IS NOT NULL THEN 'price'::price_kind "
            "                      ELSE 'unknown'::price_kind END"
        )
    )

    # Now enforce NOT NULL with a server_default so future inserts without
    # explicit price_kind get 'unknown'.
    op.alter_column(
        "listing_snapshot",
        "price_kind",
        nullable=False,
        server_default="unknown",
    )

    # ------------------------------------------------------------------
    # 12. Drop server_default='oth' from five source columns
    # Forces application code to specify source explicitly on every insert.
    # Columns remain NOT NULL — this just removes the implicit fallback.
    # ------------------------------------------------------------------
    for table in _SOURCE_TABLES:
        op.alter_column(table, "source", server_default=None)


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Restore server_default='oth' on the five source columns
    # ------------------------------------------------------------------
    for table in _SOURCE_TABLES:
        op.alter_column(table, "source", server_default="oth")

    # ------------------------------------------------------------------
    # Drop price_kind, price_high, price_display from listing_snapshot
    # ------------------------------------------------------------------
    op.drop_column("listing_snapshot", "price_kind")
    price_kind_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_column("listing_snapshot", "price_high")
    op.drop_column("listing_snapshot", "price_display")

    # ------------------------------------------------------------------
    # listing: drop partial index; rename external_listing_id → oth_listing_id
    # ------------------------------------------------------------------
    op.drop_index(
        "uq_listing_source_external_listing_id",
        table_name="listing",
        postgresql_where=sa.text("external_listing_id IS NOT NULL"),
    )
    op.alter_column("listing", "external_listing_id", new_column_name="oth_listing_id")

    # ------------------------------------------------------------------
    # property: restore old constraints; rename back
    # ------------------------------------------------------------------
    op.drop_constraint("uq_property_source_address_postcode", "property", type_="unique")
    op.create_unique_constraint(
        "uq_property_address_postcode",
        "property",
        ["formatted_address", "postcode"],
    )
    op.drop_index(
        "uq_property_source_external_property_id",
        table_name="property",
        postgresql_where=sa.text("external_property_id IS NOT NULL"),
    )
    op.alter_column("property", "external_property_id", new_column_name="oth_property_id")
    op.create_unique_constraint(
        "uq_property_oth_property_id",
        "property",
        ["oth_property_id"],
    )

    # ------------------------------------------------------------------
    # suburb: restore old constraint; rename back
    # ------------------------------------------------------------------
    op.drop_constraint("uq_suburb_source_name_postcode_state", "suburb", type_="unique")
    op.create_unique_constraint(
        "uq_suburb_name_postcode_state",
        "suburb",
        ["name", "postcode", "state"],
    )
    op.alter_column("suburb", "slug", new_column_name="oth_slug")
