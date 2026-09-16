"""Telegram alerts and alert_log table.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "procedure_id",
            sa.Integer(),
            sa.ForeignKey("procedure.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="telegram"),
        sa.Column("recipient", sa.String(length=64), nullable=False, index=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="sent"),
        sa.Column("message_preview", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "procedure_id",
            "channel",
            "recipient",
            name="uq_alert_procedure_channel_recipient",
        ),
    )
    op.create_index("ix_alert_log_created_at", "alert_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_alert_log_created_at", table_name="alert_log")
    op.drop_table("alert_log")
