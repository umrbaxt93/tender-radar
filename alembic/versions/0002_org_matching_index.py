"""Case-insensitive trigram index for organization alias matching

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alias matching compares lower(name_raw), so the index has to be on the same
    # expression or PostgreSQL cannot use it.
    op.execute(
        "CREATE INDEX ix_organization_alias_name_lower_trgm ON organization_alias "
        "USING gin (lower(name_raw) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_organization_alias_name_lower_trgm")
