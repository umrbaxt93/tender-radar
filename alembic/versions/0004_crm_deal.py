"""CRM deal and task tracking tables for Bitrix24 integration

Revision ID: 0004
Revises: 0003
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_deal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("procedure_id", sa.Integer(), sa.ForeignKey("procedure.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("deal_id", sa.String(64), nullable=False),
        sa.Column("customer_org_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="CREATED"),
        sa.Column("bitrix_response", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crm_deal_procedure_id", "crm_deal", ["procedure_id"])
    op.create_index("ix_crm_deal_customer_org_id", "crm_deal", ["customer_org_id"])

    op.create_table(
        "crm_task",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_org_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="SET NULL"), nullable=True),
        sa.Column("procedure_id", sa.Integer(), sa.ForeignKey("procedure.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=False, server_default="TAKTAK_TAYYORLASH"),
        sa.Column("task_title", sa.Text(), nullable=False),
        sa.Column("assigned_staff_id", sa.String(64), nullable=True),
        sa.Column("assigned_staff_name", sa.String(128), nullable=True),
        sa.Column("proposal_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="YANGI"),
        sa.Column("bitrix_deal_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crm_task_customer_org_id", "crm_task", ["customer_org_id"])
    op.create_index("ix_crm_task_procedure_id", "crm_task", ["procedure_id"])


def downgrade() -> None:
    op.drop_index("ix_crm_task_procedure_id", table_name="crm_task")
    op.drop_index("ix_crm_task_customer_org_id", table_name="crm_task")
    op.drop_table("crm_task")

    op.drop_index("ix_crm_deal_customer_org_id", table_name="crm_deal")
    op.drop_index("ix_crm_deal_procedure_id", table_name="crm_deal")
    op.drop_table("crm_deal")
