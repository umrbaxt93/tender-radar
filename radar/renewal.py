"""Renewal opportunity computation and the Radar query.

expected_renewal_at = completed_at + lifecycle months, with calendar month-end clamping
(31 Jan + 1 month = 28/29 Feb). contact_by_at = expected_renewal_at - contact_lead_days.
Recomputation is idempotent: every row is rebuilt from the current classification state, so
running `renewal` twice never produces duplicates.
"""

from __future__ import annotations

import bisect
import calendar
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from radar.models import (
    Award,
    Classification,
    Organization,
    Procedure,
    RenewalOpportunity,
)

log = logging.getLogger(__name__)
LIFECYCLE_PATH = Path(__file__).with_name("lifecycle.yaml")


@lru_cache(maxsize=1)
def load_lifecycle(path: Path = LIFECYCLE_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def add_months(moment: datetime, months: int) -> datetime:
    """Calendar month addition that clamps to the end of the target month."""
    total = moment.month - 1 + months
    year = moment.year + total // 12
    month = total % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def lifecycle_for(category: str | None, is_subscription: bool, term_months: int | None,
                  config: dict[str, Any] | None = None) -> tuple[int, bool]:
    """Return (months, on_radar_by_default) for a classified lot."""
    config = config or load_lifecycle()
    entry = (config["categories"] or {}).get(category or "", None)
    if entry:
        months, radar = int(entry["months"]), bool(entry["radar"])
    elif is_subscription:
        months, radar = int(config["defaults"]["subscription_months"]), True
    else:
        months, radar = int(config["defaults"]["hardware_months"]), False
    if term_months and 1 <= term_months <= 120:
        months = term_months
    return months, radar


@dataclass
class ScoreInput:
    days_to_contact: int
    amount: Decimal | None
    category_median: Decimal | None
    repeat_customer: bool
    brand: str | None


def score_opportunity(data: ScoreInput, config: dict[str, Any] | None = None) -> int:
    config = config or load_lifecycle()
    weights = config["scoring"]
    score = 0
    # Buckets are exclusive (DECISIONS.md). An overdue contact date is at least as urgent as
    # one due today, so it lands in the first bucket rather than scoring nothing.
    if data.days_to_contact <= 30:
        score += weights["contact_within_30_days"]
    elif data.days_to_contact <= 60:
        score += weights["contact_within_31_60_days"]
    if data.amount is not None and data.category_median is not None \
            and data.amount > data.category_median:
        score += weights["amount_above_category_median"]
    if data.repeat_customer:
        score += weights["repeat_customer_12_months"]
    if data.brand and data.brand in (config.get("priority_brands") or []):
        score += weights["priority_brand"]
    return score


def _category_medians(session: Session) -> dict[str, Decimal]:
    amount = func.coalesce(Award.amount, Procedure.start_price)
    rows = session.execute(
        select(Classification.category,
               func.percentile_cont(0.5).within_group(amount.asc()))
        .join(Procedure, Procedure.id == Classification.procedure_id)
        .join(Award, Award.procedure_id == Procedure.id, isouter=True)
        .where(Classification.is_it.is_(True), Classification.category.is_not(None),
               amount.is_not(None))
        .group_by(Classification.category)
    ).all()
    return {category: Decimal(str(median)) for category, median in rows if median is not None}


def _purchase_dates(session: Session) -> dict[int, list[datetime]]:
    """Completed IT purchase dates per customer, sorted, for the repeat-buyer rule."""
    rows = session.execute(
        select(Procedure.customer_org_id, Procedure.completed_at)
        .join(Classification, Classification.procedure_id == Procedure.id)
        .where(Classification.is_it.is_(True), Procedure.customer_org_id.is_not(None),
               Procedure.completed_at.is_not(None))
    ).all()
    dates: dict[int, list[datetime]] = {}
    for org_id, completed in rows:
        dates.setdefault(org_id, []).append(completed)
    for values in dates.values():
        values.sort()
    return dates


def compute_renewals(session: Session, now: datetime | None = None) -> int:
    """Rebuild renewal_opportunity from the current classifications. Idempotent."""
    now = now or datetime.now(UTC)
    config = load_lifecycle()
    lead_days = int(config["contact_lead_days"])
    medians = _category_medians(session)
    purchases = _purchase_dates(session)

    amount_col = func.coalesce(Award.amount, Procedure.start_price)
    rows = session.execute(
        select(Procedure.id, Procedure.customer_org_id, Procedure.completed_at, amount_col,
               Classification.category, Classification.brand, Classification.is_subscription,
               Classification.term_months)
        .join(Classification, Classification.procedure_id == Procedure.id)
        .join(Award, Award.procedure_id == Procedure.id, isouter=True)
        .where(Classification.is_it.is_(True), Procedure.completed_at.is_not(None))
    ).all()

    session.execute(delete(RenewalOpportunity))
    created = 0
    for pid, org_id, completed, amount, category, brand, is_sub, term in rows:
        months, on_radar = lifecycle_for(category, is_sub, term, config)
        if not on_radar and not is_sub:
            continue  # hardware without a subscription never renews on the Radar
        expected = add_months(completed, months)
        contact_by = expected - timedelta(days=lead_days)
        window = [d for d in purchases.get(org_id or -1, [])]
        repeat = False
        if window:
            lo = bisect.bisect_left(window, completed - timedelta(days=365))
            hi = bisect.bisect_right(window, completed)
            repeat = (hi - lo) >= 2
        score = score_opportunity(ScoreInput(
            days_to_contact=(contact_by - now).days,
            amount=Decimal(str(amount)) if amount is not None else None,
            category_median=medians.get(category or ""),
            repeat_customer=repeat,
            brand=brand,
        ), config)
        session.add(RenewalOpportunity(
            customer_org_id=org_id, procedure_id=pid, category=category, brand=brand,
            last_purchase_at=completed, lifecycle_months=months, expected_renewal_at=expected,
            contact_by_at=contact_by, amount=amount, score=score, computed_at=now,
        ))
        created += 1
    session.commit()
    log.info("recomputed %d renewal opportunities", created)
    return created


@dataclass
class RadarRow:
    customer: str
    stir: str | None
    region: str | None
    category: str | None
    brand: str | None
    last_purchase_at: datetime | None
    amount: Decimal | None
    expected_renewal_at: datetime | None
    contact_by_at: datetime | None
    score: int
    source_url: str | None
    title: str


def radar_rows(session: Session, now: datetime | None = None,
               limit: int | None = None, window_days: int | None = None) -> list[RadarRow]:
    """Opportunities whose contact window is open, highest score first."""
    now = now or datetime.now(UTC)
    config = load_lifecycle()
    window = timedelta(days=window_days if window_days is not None
                       else int(config["radar_contact_window_days"]))
    stmt = (select(RenewalOpportunity, Organization, Procedure)
            .join(Organization, Organization.id == RenewalOpportunity.customer_org_id,
                  isouter=True)
            .join(Procedure, Procedure.id == RenewalOpportunity.procedure_id)
            .where(RenewalOpportunity.expected_renewal_at >= now,
                   RenewalOpportunity.contact_by_at <= now + window)
            .order_by(RenewalOpportunity.score.desc(),
                      RenewalOpportunity.contact_by_at.asc()))
    if limit:
        stmt = stmt.limit(limit)
    rows = []
    for opp, org, proc in session.execute(stmt).all():
        rows.append(RadarRow(
            customer=org.name_canonical if org else "(unknown)",
            stir=org.stir if org else None,
            region=org.region if org else None,
            category=opp.category, brand=opp.brand,
            last_purchase_at=opp.last_purchase_at, amount=opp.amount,
            expected_renewal_at=opp.expected_renewal_at, contact_by_at=opp.contact_by_at,
            score=opp.score, source_url=proc.source_url, title=proc.title,
        ))
    return rows
