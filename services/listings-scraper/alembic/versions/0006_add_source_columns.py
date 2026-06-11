"""add source columns (additive only, defaults 'oth')

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-19 00:00:00.000000

Adds a `source` enum column to five tables: suburb, property, listing,
scrape_job, and scrape_list. All existing rows backfill automatically via
`server_default='oth'`. No renames are performed in this migration — PR 2's
`0007_rename_external_ids_and_price` handles the destructive rename of
`oth_property_id`, `oth_listing_id`, and `oth_slug`.

Rollback: drops the `source` column from each table and drops the
`vendor` enum type. If any `source='domain'` rows were written between
forward and rollback, they will be lost — document this before applying to
production.

Sanity check after migration:
  SELECT count(*) FROM suburb WHERE source = 'oth';  -- should be 113
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

vendor_enum = sa.Enum("oth", "domain", name="vendor")

_TABLES = ("suburb", "property", "listing", "scrape_job", "scrape_list")


def upgrade() -> None:
    vendor_enum.create(op.get_bind(), checkfirst=True)
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "source",
                vendor_enum,
                nullable=False,
                server_default="oth",
            ),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "source")
    vendor_enum.drop(op.get_bind(), checkfirst=True)
