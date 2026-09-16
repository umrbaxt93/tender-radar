"""Data retention cleanup for raw snapshots.

In compliance with Law of the Republic of Uzbekistan No. ZRU-547 "On Personal Data"
and data minimization principles, raw network snapshots (raw_snapshot) are retained
for a maximum operational window (default 365 days) and systematically cleaned up.
All cleanup operations are audit-logged.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from radar.models import RawSnapshot, User
from radar.privacy import record_audit_event

log = logging.getLogger(__name__)

_RETENTION_REGEX = re.compile(r"^(\d+)([dy])$", re.IGNORECASE)


def parse_retention_period(period_str: str) -> int:
    """Parse retention string like '365d' or '1y' into number of days."""
    match = _RETENTION_REGEX.match(period_str.strip())
    if not match:
        raise ValueError(
            f"Invalid retention period: {period_str!r}. "
            "Expected format like '365d' (days) or '1y' (years)."
        )
    value, unit = match.groups()
    num = int(value)
    if num <= 0:
        raise ValueError(f"Retention period must be positive, got {num}")

    if unit.lower() == "d":
        return num
    elif unit.lower() == "y":
        return num * 365
    raise ValueError(f"Unknown retention unit: {unit!r}")


def cleanup_old_snapshots(
    session: Session,
    older_than_days: int = 365,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Delete raw snapshots older than specified days and record an audit log event.

    Args:
        session: Active SQLAlchemy database session.
        older_than_days: Number of days threshold (default 365).
        user_id: User ID responsible for cleanup (defaults to first admin user if available).

    Returns:
        Dict with cleanup statistics (e.g. {'deleted_snapshots': int, 'cutoff': str}).
    """
    if older_than_days <= 0:
        raise ValueError(f"older_than_days must be positive, got {older_than_days}")

    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

    # Resolve user_id for audit logging
    if user_id is None:
        admin_user = session.query(User).filter(User.role == "admin").order_by(User.id).first()
        if not admin_user:
            admin_user = session.query(User).order_by(User.id).first()
        if admin_user:
            user_id = admin_user.id

    # Execute deletion
    stmt = delete(RawSnapshot).where(RawSnapshot.fetched_at < cutoff)
    result = session.execute(stmt)
    deleted_count = result.rowcount

    # Log to audit_log if user_id is present
    if user_id is not None:
        record_audit_event(
            session,
            user_id=user_id,
            action="cleanup_snapshots",
            target_type="raw_snapshot",
            details={
                "older_than_days": older_than_days,
                "deleted": deleted_count,
                "cutoff": cutoff.isoformat(),
            },
        )

    log.info(
        "Cleaned up %d raw snapshots older than %d days (cutoff: %s)",
        deleted_count,
        older_than_days,
        cutoff.isoformat(),
    )

    return {
        "deleted_snapshots": deleted_count,
        "cutoff": cutoff.isoformat(),
        "older_than_days": older_than_days,
    }
