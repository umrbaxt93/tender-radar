"""Data quality, dedup support, classification needs_review, and v_dashboard_stats view.

Revision ID: 0006
Revises: 0005
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create durable backup table for renewal opportunities before applying any dedup
    op.execute(
        "CREATE TABLE IF NOT EXISTS renewal_opportunity_backup AS "
        "SELECT * FROM renewal_opportunity;"
    )

    # 2. Add merged_from_id to procedure for cross-source and intra-source deduplication
    op.add_column(
        "procedure",
        sa.Column(
            "merged_from_id",
            sa.Integer(),
            sa.ForeignKey("procedure.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_procedure_merged_from_id", "procedure", ["merged_from_id"])

    # 3. Add needs_review to classification for low confidence (< 0.7) AI classifications
    op.add_column(
        "classification",
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # 4. Enforce unique constraint on (customer_org_id, procedure_id) for renewal_opportunity
    op.create_unique_constraint(
        "uq_renewal_customer_procedure",
        "renewal_opportunity",
        ["customer_org_id", "procedure_id"],
    )

    # 5. Create SQL view v_dashboard_stats for consistent platform metrics
    op.execute("""
        CREATE OR REPLACE VIEW v_dashboard_stats AS
        SELECT
            COUNT(p.id) AS total_procedures,
            COUNT(p.id) FILTER (WHERE p.source = 'uzex') AS uzex_count,
            COUNT(p.id) FILTER (WHERE p.source = 'ebirja') AS ebirja_count,
            COUNT(p.id) FILTER (WHERE p.source = 'xt_xarid') AS xt_count,
            COUNT(p.id) FILTER (WHERE p.source NOT IN ('uzex', 'ebirja', 'xt_xarid')) AS other_count,
            COUNT(DISTINCT p.customer_org_id) AS total_customers,
            COUNT(DISTINCT a.supplier_org_id) AS total_suppliers,
            COALESCE(SUM(COALESCE(a.amount, p.start_price, 0)), 0) AS total_amount,
            COUNT(c.procedure_id) FILTER (WHERE c.is_it IS TRUE) AS total_it_lots,
            COUNT(c.procedure_id) FILTER (WHERE c.is_it IS TRUE AND c.needs_review IS TRUE) AS needs_review_count
        FROM procedure p
        LEFT JOIN award a ON a.procedure_id = p.id
        LEFT JOIN classification c ON c.procedure_id = p.id
        WHERE p.merged_from_id IS NULL;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_dashboard_stats;")
    op.drop_constraint("uq_renewal_customer_procedure", "renewal_opportunity", type_="unique")
    op.drop_column("classification", "needs_review")
    op.drop_index("ix_procedure_merged_from_id", table_name="procedure")
    op.drop_column("procedure", "merged_from_id")
