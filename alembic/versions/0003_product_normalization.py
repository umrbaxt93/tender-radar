"""Product normalization columns on lot_item (brand, product_family, model, term_months)

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lot_item", sa.Column("brand", sa.Text(), nullable=True))
    op.add_column("lot_item", sa.Column("product_family", sa.Text(), nullable=True))
    op.add_column("lot_item", sa.Column("model", sa.Text(), nullable=True))
    op.add_column("lot_item", sa.Column("term_months", sa.Integer(), nullable=True))
    op.create_index("ix_lot_item_brand", "lot_item", ["brand"])


def downgrade() -> None:
    op.drop_index("ix_lot_item_brand", table_name="lot_item")
    op.drop_column("lot_item", "term_months")
    op.drop_column("lot_item", "model")
    op.drop_column("lot_item", "product_family")
    op.drop_column("lot_item", "brand")
