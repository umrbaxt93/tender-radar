"""Comprehensive test suite for Phase 1 Data Quality and Deduplication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from radar.auth import SESSION_COOKIE_NAME, create_session_token, hash_password
from radar.classify.pipeline import recheck_classifications
from radar.classify.rules import classify_procedure
from radar.db import session_scope
from radar.dedup import find_and_merge_duplicates
from radar.models import (
    AiCache,
    Award,
    Classification,
    Organization,
    Procedure,
    RenewalOpportunity,
    User,
)
from radar.renewal import ScoreInput, compute_renewals, score_opportunity
from radar.web import app

client = TestClient(app)
NOW = datetime(2026, 9, 15, tzinfo=UTC)


@pytest.fixture
def admin_user():
    """Create an admin user for review endpoint testing."""
    username = "test_admin_dq"
    pwd = "AdminSecurePassword123!"
    with session_scope() as session:
        user = session.scalar(select(User).where(User.username == username))
        if not user:
            user = User(
                username=username,
                password_hash=hash_password(pwd),
                role="admin",
                is_active=True,
            )
            session.add(user)
            session.commit()
        user_id = user.id

    yield {"id": user_id, "username": username, "role": "admin"}

    with session_scope() as session:
        u = session.get(User, user_id)
        if u:
            session.delete(u)
            session.commit()


@pytest.fixture
def sales_user():
    """Create a sales user (non-admin) for RBAC testing."""
    username = "test_sales_dq"
    pwd = "SalesSecurePassword123!"
    with session_scope() as session:
        user = session.scalar(select(User).where(User.username == username))
        if not user:
            user = User(
                username=username,
                password_hash=hash_password(pwd),
                role="sales",
                is_active=True,
            )
            session.add(user)
            session.commit()
        user_id = user.id

    yield {"id": user_id, "username": username, "role": "sales"}

    with session_scope() as session:
        u = session.get(User, user_id)
        if u:
            session.delete(u)
            session.commit()


def test_generator_is_not_ups():
    """Verify diesel/gas generators are NOT classified as IT or UPS."""
    res1 = classify_procedure("Dizel generator 50 kVA avtomatika bilan", ["Dizel generator"])
    assert res1.likely_it == "no"
    assert res1.category != "UPS"

    res2 = classify_procedure("Benzinli generator 5 kVA", ["Benzin generator"])
    assert res2.likely_it == "no"

    # Real UPS must still be classified as IT UPS
    res3 = classify_procedure("Uzluksiz quvvat manbai (UPS) 1500VA", ["Smart UPS 1500"])
    assert res3.likely_it == "yes"
    assert res3.category == "UPS"


def test_ispring_is_not_google_workspace():
    """Verify 'iSpring Suite' does not match 'g suite' regex and is Software Licenses."""
    res = classify_procedure("iSpring Suite Max litsenziyasi 1 yil", ["iSpring Suite Max"])
    assert res.category == "Software Licenses"
    assert res.brand == "iSpring"
    assert res.brand != "Google"
    assert res.category != "Google Workspace"


def test_not_it_keywords_block_non_it_lots():
    """Verify additional negative keywords (ads, events, construction) are rejected."""
    cases = [
        ("Reklama xizmatlari va bannerlar tayyorlash", ["Banner tayyorlash"]),
        ("Blogerlar orqali targ'ibot xizmatlari", ["Bloger xizmati"]),
        ("Bayram tadbiri va yubiley tashkil etish", ["Tadbir tashkil etish"]),
        ("Qurilish-montaj va o'lchov ishlari", ["Montaj xizmatlari"]),
        ("ISO konsalting va xodimlar treningi", ["Trening xizmati"]),
    ]
    for title, items in cases:
        decision = classify_procedure(title, items)
        assert decision.likely_it == "no", f"Failed for {title}: got {decision.likely_it}"


def test_dedup_idempotent_and_merges_duplicates(session):
    """Verify cross-source deduplication links duplicate procedure and removes renewal."""
    cust = Organization(stir="309999991", name_canonical="Customer DQ Org", region="Toshkent")
    supp = Organization(stir="309999992", name_canonical="Supplier DQ Org", region="Toshkent")
    session.add_all([cust, supp])
    session.flush()

    p1 = Procedure(
        source="uzex",
        source_id="UZ-DQ-100",
        title="Server uskunalari xaridi",
        customer_org_id=cust.id,
        completed_at=NOW - timedelta(days=10),
        start_price=Decimal("150000000"),
    )
    p2 = Procedure(
        source="ebirja",
        source_id="EB-DQ-200",
        title="Server uskunalari xaridi (birja)",
        customer_org_id=cust.id,
        completed_at=NOW - timedelta(days=9),  # 1 day difference (within 3 days)
        start_price=Decimal("150000000"),
    )
    session.add_all([p1, p2])
    session.flush()

    a1 = Award(procedure_id=p1.id, supplier_org_id=supp.id, amount=Decimal("145000000"))
    a2 = Award(procedure_id=p2.id, supplier_org_id=supp.id, amount=Decimal("145000000"))
    session.add_all([a1, a2])

    c1 = Classification(
        procedure_id=p1.id, is_it=True, category="Server", is_subscription=True,
        confidence=0.9, method="rule",
    )
    c2 = Classification(
        procedure_id=p2.id, is_it=True, category="Server", is_subscription=True,
        confidence=0.9, method="rule",
    )
    session.add_all([c1, c2])
    session.commit()

    compute_renewals(session, now=NOW)
    # Both had renewals initially
    ro1 = session.scalar(select(RenewalOpportunity).where(RenewalOpportunity.procedure_id == p1.id))
    ro2 = session.scalar(select(RenewalOpportunity).where(RenewalOpportunity.procedure_id == p2.id))
    assert ro1 is not None
    assert ro2 is not None

    # Run dedup
    result = find_and_merge_duplicates(session)
    assert result["merged"] >= 1

    # p2 should be merged into p1
    session.refresh(p2)
    assert p2.merged_from_id == p1.id

    # p2 renewal must be deleted
    ro2_after = session.scalar(
        select(RenewalOpportunity).where(RenewalOpportunity.procedure_id == p2.id)
    )
    assert ro2_after is None

    # p1 renewal remains intact
    ro1_after = session.scalar(
        select(RenewalOpportunity).where(RenewalOpportunity.procedure_id == p1.id)
    )
    assert ro1_after is not None

    # Dedup must be idempotent
    rerun = find_and_merge_duplicates(session)
    assert rerun["merged"] == 0


def test_low_confidence_marks_needs_review(session):
    """Verify AI confidence < 0.7 sets needs_review=True and excludes from renewals."""
    cust = Organization(stir="309999993", name_canonical="Customer Review Org", region="Toshkent")
    session.add(cust)
    session.flush()

    p = Procedure(
        source="uzex",
        source_id="UZ-DQ-300",
        title="Noma'lum IT dastur",
        customer_org_id=cust.id,
        completed_at=NOW - timedelta(days=20),
        start_price=Decimal("20000000"),
    )
    session.add(p)
    session.flush()

    c = Classification(
        procedure_id=p.id,
        is_it=True,
        category="Software Licenses",
        confidence=0.55,  # Low confidence < 0.7
        method="ai",
        needs_review=False,
    )
    session.add(c)
    session.commit()

    # Recheck classifications
    recheck_classifications(session)
    session.refresh(c)
    assert c.needs_review is True

    # Renewals must exclude procedures with needs_review=True
    compute_renewals(session, now=NOW)
    ro = session.scalar(select(RenewalOpportunity).where(RenewalOpportunity.procedure_id == p.id))
    assert ro is None


def test_v_dashboard_stats_view_sum_invariant(session):
    """Verify v_dashboard_stats SQL view guarantees sum invariant across platforms."""
    row = session.execute(text("SELECT * FROM v_dashboard_stats")).mappings().first()
    assert row is not None
    total = row["total_procedures"]
    parts = row["uzex_count"] + row["ebirja_count"] + row["xt_count"] + row["other_count"]
    assert total == parts


def test_score_0_to_100_thresholds():
    """Verify the enriched 0-100 scoring logic, bonus factors, and capping at 100."""
    # Base urgency test
    base = ScoreInput(
        days_to_contact=15,
        amount=Decimal("10000000"),
        category_median=Decimal("20000000"),
        repeat_customer=False,
        brand=None,
        previous_winner_softy=False,
        previous_winner_competitor=False,
        explicit_term=False,
    )
    # Urgency <= 30 gives 40
    assert score_opportunity(base) == 40

    # Max combination without cap:
    # 40 (urgency) + 15 (amount) + 10 (repeat) + 10 (brand) + 15 (softy) + 10 (explicit) = 100
    max_input = ScoreInput(
        days_to_contact=5,
        amount=Decimal("50000000"),
        category_median=Decimal("20000000"),
        repeat_customer=True,
        brand="Fortinet",
        previous_winner_softy=True,
        previous_winner_competitor=False,
        explicit_term=True,
    )
    score_max = score_opportunity(max_input)
    assert score_max == 100
    assert score_max >= 80  # HOT

    # Competitor winner (+5) instead of softy
    comp_input = ScoreInput(
        days_to_contact=45,  # 25 points
        amount=Decimal("10000000"),
        category_median=Decimal("20000000"),
        repeat_customer=False,
        brand=None,
        previous_winner_softy=False,
        previous_winner_competitor=True,  # +5
        explicit_term=False,
    )
    assert score_opportunity(comp_input) == 30  # 25 + 5 = 30 (COLD < 50)


def test_admin_review_endpoints(admin_user, sales_user):
    """Verify RBAC on /admin/review and POST /api/admin/review/{id} updating without ai_cache."""
    with session_scope() as session:
        cust = session.scalar(select(Organization).where(Organization.stir == "309999994"))
        if not cust:
            cust = Organization(
                stir="309999994", name_canonical="Customer Review RBAC", region="Toshkent"
            )
            session.add(cust)
            session.flush()

        old_proc = session.scalar(select(Procedure).where(Procedure.source_id == "UZ-DQ-400"))
        if old_proc:
            old_c = session.get(Classification, old_proc.id)
            if old_c:
                session.delete(old_c)
            session.delete(old_proc)
            session.flush()

        proc = Procedure(
            source="uzex",
            source_id="UZ-DQ-400",
            title="Shubhali litsenziya",
            customer_org_id=cust.id,
            completed_at=NOW - timedelta(days=15),
            start_price=Decimal("30000000"),
        )
        session.add(proc)
        session.flush()
        proc_id = proc.id

        c = Classification(
            procedure_id=proc.id,
            is_it=True,
            category="Other",
            confidence=0.5,
            method="ai",
            needs_review=True,
        )
        session.add(c)
        session.commit()

    admin_token = create_session_token(admin_user["id"], admin_user["username"], "admin")
    sales_token = create_session_token(sales_user["id"], sales_user["username"], "sales")

    # 1. Sales user cannot access /admin/review (403 Forbidden)
    client.cookies.set(SESSION_COOKIE_NAME, sales_token)
    res_sales = client.get("/admin/review")
    assert res_sales.status_code == 403

    try:
        # 2. Admin can access /admin/review (200 OK)
        client.cookies.set(SESSION_COOKIE_NAME, admin_token)
        res_admin = client.get("/admin/review")
        assert res_admin.status_code == 200
        assert "UZ-DQ-400" in res_admin.text or "Shubhali litsenziya" in res_admin.text

        # 3. Sales user cannot POST /api/admin/review/{id} (403)
        client.cookies.set(SESSION_COOKIE_NAME, sales_token)
        res_post_sales = client.post(
            f"/api/admin/review/{proc_id}",
            json={"category": "Software Licenses", "is_it": True, "brand": "Microsoft"},
        )
        assert res_post_sales.status_code == 403

        # Initial ai_cache count
        with session_scope() as session:
            cache_count_before = session.scalar(select(func.count()).select_from(AiCache)) or 0

        # 4. Admin submits review
        client.cookies.set(SESSION_COOKIE_NAME, admin_token)
        res_post_admin = client.post(
            f"/api/admin/review/{proc_id}",
            json={"category": "Software Licenses", "is_it": True, "brand": "Microsoft"},
        )
        assert res_post_admin.status_code == 200
        data = res_post_admin.json()
        assert data["status"] == "ok"

        # 5. Check classification updated to manual, needs_review=False, confidence=1.0
        with session_scope() as session:
            clf = session.get(Classification, proc_id)
            assert clf is not None
            assert clf.category == "Software Licenses"
            assert clf.brand == "Microsoft"
            assert clf.is_it is True
            assert clf.method == "manual"
            assert clf.needs_review is False
            assert clf.confidence == 1.0

            # 6. Verify ai_cache was NOT polluted
            cache_count_after = session.scalar(select(func.count()).select_from(AiCache)) or 0
            assert cache_count_after == cache_count_before
    finally:
        client.cookies.clear()
        with session_scope() as session:
            c_del = session.get(Classification, proc_id)
            if c_del:
                session.delete(c_del)
            p_del = session.get(Procedure, proc_id)
            if p_del:
                session.delete(p_del)
            session.commit()
