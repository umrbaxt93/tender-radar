"""Database counts used by the CLI, the Stats sheet and /health."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from radar.models import (
    AiCache,
    AiCostLedger,
    Award,
    Classification,
    ImportCursor,
    LotItem,
    Organization,
    Procedure,
    RawSnapshot,
    RenewalOpportunity,
)


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def collect_stats(session: Session) -> dict[str, object]:
    def count(model, *where):
        return session.scalar(select(func.count()).select_from(model).where(*where)) or 0

    cursor = session.get(ImportCursor, "uzex_completed")
    spent = session.scalar(
        select(func.coalesce(func.sum(func.coalesce(AiCostLedger.actual_usd,
                                                     AiCostLedger.estimated_usd)), 0))
        .where(AiCostLedger.status != "failed")
    )
    v_row = None
    try:
        res = session.execute(text("SELECT * FROM v_dashboard_stats")).mappings().first()
        if res:
            v_row = dict(res)
    except Exception:
        v_row = None

    if v_row:
        procedures = int(v_row["total_procedures"])
        by_source = {
            "uzex": int(v_row["uzex_count"]),
            "ebirja": int(v_row["ebirja_count"]),
            "xt_xarid": int(v_row["xt_count"]),
        }
        if v_row.get("other_count"):
            by_source["other"] = int(v_row["other_count"])
    else:
        by_source = dict(session.execute(
            select(Procedure.source, func.count()).group_by(Procedure.source)).all())
        procedures = count(Procedure)
    # Coverage tells you how much of the data the analysis can actually rely on. A Radar
    # built on lots without amounts or completion dates would look full and mean nothing.
    with_award = count(Award)
    with_completed = count(Procedure, Procedure.completed_at.is_not(None))
    with_amount = session.scalar(
        select(func.count()).select_from(Procedure)
        .outerjoin(Award, Award.procedure_id == Procedure.id)
        .where(func.coalesce(Award.amount, Procedure.start_price).is_not(None))) or 0
    with_customer = count(Procedure, Procedure.customer_org_id.is_not(None))
    lots_with_quantity = session.scalar(
        select(func.count(func.distinct(LotItem.procedure_id)))
        .where(LotItem.quantity.is_not(None))) or 0
    return {
        "procedures": procedures,
        "procedures_by_source": by_source,
        "coverage_completed_at_pct": _pct(with_completed, procedures),
        "coverage_customer_pct": _pct(with_customer, procedures),
        "coverage_amount_pct": _pct(with_amount, procedures),
        "coverage_award_pct": _pct(with_award, procedures),
        "coverage_quantity_pct": _pct(lots_with_quantity, procedures),
        "organizations": count(Organization),
        "raw_snapshots": count(RawSnapshot),
        "classified": count(Classification),
        "classified_it": count(Classification, Classification.is_it.is_(True)),
        "classified_by_rule": count(Classification, Classification.method == "rule"),
        "classified_by_ai": count(Classification, Classification.method == "ai"),
        "needs_review_count": count(Classification, Classification.needs_review.is_(True)),
        "ai_cache_entries": count(AiCache),
        "ai_calls": count(AiCostLedger),
        "ai_spent_usd": float(spent or 0),
        "renewal_opportunities": count(RenewalOpportunity),
        "cursor_last_page": cursor.last_page if cursor else 0,
        "cursor_last_source_id": cursor.last_source_id if cursor else None,
    }
