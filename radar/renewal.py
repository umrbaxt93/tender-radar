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
from sqlalchemy.orm import Session, aliased

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
    previous_winner_softy: bool = False
    previous_winner_competitor: bool = False
    explicit_term: bool = False


def score_opportunity(data: ScoreInput, config: dict[str, Any] | None = None) -> int:
    config = config or load_lifecycle()
    weights = config.get("scoring", {})
    score = 0

    # 1. Contact urgency (0-40)
    if data.days_to_contact <= 30:
        score += weights.get("contact_within_30_days", 40)
    elif data.days_to_contact <= 60:
        score += weights.get("contact_within_31_60_days", 25)

    # 2. Amount above category median (0-15)
    if (
        data.amount is not None
        and data.category_median is not None
        and data.amount > data.category_median
    ):
        score += weights.get("amount_above_category_median", 15)

    # 3. Repeat customer: >=2 IT purchases in last 12 months (0-10)
    if data.repeat_customer:
        score += weights.get("repeat_customer_12_months", 10)

    # 4. Priority brand (0-10)
    if data.brand and data.brand in (config.get("priority_brands") or []):
        score += weights.get("priority_brand", 10)

    # 5. Previous winner: Softy (+15) or Competitor (+5)
    if data.previous_winner_softy:
        score += weights.get("previous_winner_softy", 15)
    elif data.previous_winner_competitor:
        score += weights.get("previous_winner_competitor", 5)

    # 6. Explicit term extracted from contract (+10)
    if data.explicit_term:
        score += weights.get("explicit_term_reliability", 10)

    return min(score, 100)


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
    supplier_org = aliased(Organization, name="supplier_org")
    rows = session.execute(
        select(
            Procedure.id,
            Procedure.customer_org_id,
            Procedure.completed_at,
            amount_col,
            Classification.category,
            Classification.brand,
            Classification.is_subscription,
            Classification.term_months,
            supplier_org.name_canonical,
        )
        .join(Classification, Classification.procedure_id == Procedure.id)
        .join(Award, Award.procedure_id == Procedure.id, isouter=True)
        .join(supplier_org, supplier_org.id == Award.supplier_org_id, isouter=True)
        .where(
            Classification.is_it.is_(True),
            Classification.needs_review.is_(False),
            Procedure.merged_from_id.is_(None),
            Procedure.completed_at.is_not(None),
        )
    ).all()

    session.execute(delete(RenewalOpportunity))
    created = 0
    for pid, org_id, completed, amount, category, brand, is_sub, term, supp_name in rows:
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

        softy_won = False
        competitor_won = False
        if supp_name:
            if "softy" in supp_name.lower():
                softy_won = True
            else:
                competitor_won = True

        explicit_term = bool(term and 1 <= term <= 120)

        score = score_opportunity(
            ScoreInput(
                days_to_contact=(contact_by - now).days,
                amount=Decimal(str(amount)) if amount is not None else None,
                category_median=medians.get(category or ""),
                repeat_customer=repeat,
                brand=brand,
                previous_winner_softy=softy_won,
                previous_winner_competitor=competitor_won,
                explicit_term=explicit_term,
            ),
            config,
        )
        session.add(
            RenewalOpportunity(
                customer_org_id=org_id,
                procedure_id=pid,
                category=category,
                brand=brand,
                last_purchase_at=completed,
                lifecycle_months=months,
                expected_renewal_at=expected,
                contact_by_at=contact_by,
                amount=amount,
                score=score,
                computed_at=now,
            )
        )
        created += 1
    session.commit()
    log.info("recomputed %d renewal opportunities", created)
    return created


@dataclass
class RadarRow:
    procedure_id: int
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


def radar_rows(
    session: Session,
    now: datetime | None = None,
    limit: int | None = None,
    offset: int = 0,
    window_days: int | None = None,
    category: str | None = None,
    brand: str | None = None,
    min_amount: float | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    return_total: bool = False,
) -> list[RadarRow] | tuple[list[RadarRow], int]:
    """Opportunities whose contact window is open, highest score first."""
    now = now or datetime.now(UTC)
    config = load_lifecycle()
    window = timedelta(
        days=window_days if window_days is not None else int(config["radar_contact_window_days"])
    )
    stmt = (
        select(RenewalOpportunity, Organization, Procedure)
        .join(
            Organization,
            Organization.id == RenewalOpportunity.customer_org_id,
            isouter=True,
        )
        .join(Procedure, Procedure.id == RenewalOpportunity.procedure_id)
        .where(
            Procedure.merged_from_id.is_(None),
            RenewalOpportunity.expected_renewal_at >= now,
            RenewalOpportunity.contact_by_at <= now + window,
        )
    )

    if category:
        stmt = stmt.where(RenewalOpportunity.category == category)
    if brand:
        stmt = stmt.where(RenewalOpportunity.brand.ilike(f"%{brand}%"))
    if min_amount is not None:
        stmt = stmt.where(RenewalOpportunity.amount >= min_amount)
    if date_from is not None:
        stmt = stmt.where(RenewalOpportunity.contact_by_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(RenewalOpportunity.contact_by_at <= date_to)

    total_count = 0
    if return_total:
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = session.scalar(count_stmt) or 0

    stmt = stmt.order_by(
        RenewalOpportunity.score.desc(),
        RenewalOpportunity.contact_by_at.asc(),
    )

    if offset:
        stmt = stmt.offset(offset)
    if limit:
        stmt = stmt.limit(limit)

    rows = []
    for opp, org, proc in session.execute(stmt).all():
        rows.append(
            RadarRow(
                procedure_id=proc.id,
                customer=org.name_canonical if org else "(unknown)",
                stir=org.stir if org else None,
                region=org.region if org else None,
                category=opp.category,
                brand=opp.brand,
                last_purchase_at=opp.last_purchase_at,
                amount=opp.amount,
                expected_renewal_at=opp.expected_renewal_at,
                contact_by_at=opp.contact_by_at,
                score=opp.score,
                source_url=proc.source_url,
                title=proc.title,
            )
        )
    if return_total:
        return rows, total_count
    return rows
