"""Add listing.sale_date DATE NULLABLE

Revision ID: 0007
Revises: 0005
Create Date: 2026-05-11 00:00:00.000000

Adds `sale_date` to the `listing` table so the reconciler can persist the
actual settled-sale date for `recentlysold` listings extracted from OTH's
`raw_payload`. The column is NULL for `forsale` and `forrent` listings and
is never overwritten once set.

Key path discovery:  OTH search-API payloads for `recentlysold` listings
carry the sale date at `lastSale.eventDate` (ISO-8601 date string,
e.g. `"2026-04-28"`). Confirmed across all 24 entries in the
`recentlysold_paddington_p0.json` fixture corpus; absent from the `forsale`
and `forrent` fixture corpora.

Note: Revision chains from 0005 because the parallel 0006 slot is reserved
for a different feature on another branch. Alembic's linear chain requires
`down_revision = "0005"`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "listing",
        sa.Column("sale_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("listing", "sale_date")
