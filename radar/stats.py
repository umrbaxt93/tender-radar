"""Database counts used by the CLI, the Stats sheet and /health."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.models import (
    AiCache,
    AiCostLedger,
    Classification,
    ImportCursor,
    Organization,
    Procedure,
    RawSnapshot,
    RenewalOpportunity,
)


def collect_stats(session: Session) -> dict[str, object]:
    def count(model, *where):
        return session.scalar(select(func.count()).select_from(model).where(*where)) or 0

    cursor = session.get(ImportCursor, "uzex_completed")
    spent = session.scalar(
        select(func.coalesce(func.sum(func.coalesce(AiCostLedger.actual_usd,
                                                     AiCostLedger.estimated_usd)), 0))
        .where(AiCostLedger.status != "failed")
    )
    by_source = dict(session.execute(
        select(Procedure.source, func.count()).group_by(Procedure.source)).all())
    return {
        "procedures": count(Procedure),
        "procedures_by_source": by_source,
        "organizations": count(Organization),
        "raw_snapshots": count(RawSnapshot),
        "classified": count(Classification),
        "classified_it": count(Classification, Classification.is_it.is_(True)),
        "classified_by_rule": count(Classification, Classification.method == "rule"),
        "classified_by_ai": count(Classification, Classification.method == "ai"),
        "ai_cache_entries": count(AiCache),
        "ai_calls": count(AiCostLedger),
        "ai_spent_usd": float(spent or 0),
        "renewal_opportunities": count(RenewalOpportunity),
        "cursor_last_page": cursor.last_page if cursor else 0,
        "cursor_last_source_id": cursor.last_source_id if cursor else None,
    }
