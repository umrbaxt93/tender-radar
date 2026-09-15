"""Renewal maths, scoring and the Radar window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from radar.models import Award, Classification, Organization, Procedure, RenewalOpportunity
from radar.renewal import (
    ScoreInput,
    add_months,
    compute_renewals,
    lifecycle_for,
    radar_rows,
    score_opportunity,
)

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def test_add_months_clamps_to_month_end():
    assert add_months(datetime(2026, 1, 31, tzinfo=UTC), 1) == datetime(2026, 2, 28, tzinfo=UTC)
    assert add_months(datetime(2024, 1, 31, tzinfo=UTC), 1) == datetime(2024, 2, 29, tzinfo=UTC)
    assert add_months(datetime(2026, 3, 31, tzinfo=UTC), 1) == datetime(2026, 4, 30, tzinfo=UTC)
    assert add_months(datetime(2026, 9, 13, tzinfo=UTC), 12) == datetime(2027, 9, 13, tzinfo=UTC)
    assert add_months(datetime(2026, 12, 15, tzinfo=UTC), 1) == datetime(2027, 1, 15, tzinfo=UTC)
    assert add_months(datetime(2026, 2, 28, tzinfo=UTC), 48) == \
        datetime(2030, 2, 28, tzinfo=UTC)


def test_lifecycle_selection():
    assert lifecycle_for("Microsoft", False, None) == (12, True)
    assert lifecycle_for("Server", False, None) == (48, False)
    # A term stated in the lot text wins over the category default.
    assert lifecycle_for("Microsoft", True, 36) == (36, True)
    # Implausible terms are ignored.
    assert lifecycle_for("Microsoft", True, 999) == (12, True)
    # Unknown category falls back on the subscription flag.
    assert lifecycle_for(None, True, None) == (12, True)
    assert lifecycle_for(None, False, None) == (48, False)


def test_score_buckets_are_exclusive_and_top_out_at_75():
    base = dict(amount=None, category_median=None, repeat_customer=False, brand=None)
    assert score_opportunity(ScoreInput(days_to_contact=10, **base)) == 40
    assert score_opportunity(ScoreInput(days_to_contact=30, **base)) == 40
    assert score_opportunity(ScoreInput(days_to_contact=31, **base)) == 25
    assert score_opportunity(ScoreInput(days_to_contact=60, **base)) == 25
    assert score_opportunity(ScoreInput(days_to_contact=61, **base)) == 0
    # An overdue contact date is at least as urgent as one due today.
    assert score_opportunity(ScoreInput(days_to_contact=-5, **base)) == 40
    full = score_opportunity(ScoreInput(days_to_contact=1, amount=Decimal("10"),
                                        category_median=Decimal("5"), repeat_customer=True,
                                        brand="Fortinet"))
    assert full == 75


def seed(session, *, completed, category, brand=None, amount=1000, is_sub=True,
         source_id="P1", org=None, is_it=True):
    if org is None:
        org = Organization(stir=f"stir-{source_id}", name_canonical=f"Org {source_id}",
                           region="Toshkent")
        session.add(org)
        session.flush()
    proc = Procedure(source="synthetic", source_id=source_id, title=f"{category} lot",
                     customer_org_id=org.id, completed_at=completed,
                     start_price=Decimal(str(amount)),
                     source_url=f"https://example.invalid/{source_id}")
    session.add(proc)
    session.flush()
    session.add(Classification(procedure_id=proc.id, is_it=is_it, category=category,
                               brand=brand, is_subscription=is_sub, method="rule"))
    session.commit()
    return org, proc


def test_expected_renewal_and_contact_date(session):
    seed(session, completed=datetime(2026, 1, 31, tzinfo=UTC), category="Microsoft")
    assert compute_renewals(session, now=NOW) == 1
    opp = session.scalar(select(RenewalOpportunity))
    assert opp.lifecycle_months == 12
    assert opp.expected_renewal_at == datetime(2027, 1, 31, tzinfo=UTC)
    assert opp.contact_by_at == datetime(2027, 1, 31, tzinfo=UTC) - timedelta(days=60)


def test_hardware_is_excluded_unless_subscription(session):
    seed(session, completed=NOW - timedelta(days=30), category="Server", is_sub=False,
         source_id="HW")
    assert compute_renewals(session, now=NOW) == 0
    seed(session, completed=NOW - timedelta(days=30), category="Server", is_sub=True,
         source_id="HW-SUB")
    assert compute_renewals(session, now=NOW) == 1


def test_non_it_and_missing_dates_are_skipped(session):
    seed(session, completed=NOW - timedelta(days=10), category=None, is_it=False,
         source_id="NONIT")
    seed(session, completed=None, category="Microsoft", source_id="NODATE")
    assert compute_renewals(session, now=NOW) == 0


def test_recomputation_is_idempotent(session):
    seed(session, completed=NOW - timedelta(days=300), category="Microsoft")
    assert compute_renewals(session, now=NOW) == 1
    assert compute_renewals(session, now=NOW) == 1
    assert session.scalar(select(func.count()).select_from(RenewalOpportunity)) == 1


def test_radar_window_and_ordering(session):
    # Contact due in ~5 days: on the radar, urgent.
    seed(session, completed=datetime(2025, 11, 17, tzinfo=UTC), category="Firewall",
         brand="Fortinet", amount=5000, source_id="SOON")
    # Contact due in ~200 days: outside the 60 day window.
    seed(session, completed=datetime(2026, 6, 1, tzinfo=UTC), category="Cloud",
         amount=10, source_id="LATER")
    # Renewal already passed: off the radar.
    seed(session, completed=datetime(2024, 1, 1, tzinfo=UTC), category="Microsoft",
         amount=10, source_id="PAST")
    compute_renewals(session, now=NOW)
    rows = radar_rows(session, now=NOW)
    assert [r.category for r in rows] == ["Firewall"]
    assert rows[0].brand == "Fortinet" and rows[0].stir == "stir-SOON"
    assert rows[0].source_url.endswith("SOON")
    assert rows[0].score >= 40
    assert len(radar_rows(session, now=NOW, window_days=400)) == 2


def test_award_amount_wins_over_start_price(session):
    _, proc = seed(session, completed=NOW - timedelta(days=300), category="Microsoft",
                   amount=1000)
    session.add(Award(procedure_id=proc.id, amount=Decimal("777")))
    session.commit()
    compute_renewals(session, now=NOW)
    assert session.scalar(select(RenewalOpportunity)).amount == Decimal("777.00")


def test_repeat_customer_bonus(session):
    org, _ = seed(session, completed=datetime(2025, 11, 17, tzinfo=UTC), category="Cloud",
                  amount=10, source_id="ONE")
    single = compute_renewals(session, now=NOW) and session.scalar(
        select(RenewalOpportunity.score))
    seed(session, completed=datetime(2025, 11, 10, tzinfo=UTC), category="Cloud", amount=10,
         source_id="TWO", org=org)
    compute_renewals(session, now=NOW)
    scores = sorted(session.scalars(select(RenewalOpportunity.score)))
    assert max(scores) == single + 10
