"""Unit tests for Tender Radar AI Procurement Advisor."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from radar.ai_advisor import generate_ai_recommendation, get_recommendation_for_procedure
from radar.models import Award, Base, Classification, LotItem, Organization, Procedure


def test_generate_ai_recommendation_offline() -> None:
    proc = {
        "title": "Dell PowerEdge Server yetkazib berish",
        "source": "ebirja",
        "source_id": "ebirja_101",
        "customer": {"name": "Aloqabank ATB", "stir": "200111222"},
        "supplier": {"name": "Smart Server MCHJ", "stir": "305111222"},
        "amount": 250_000_000,
        "currency": "UZS",
        "date": "2026-03-01",
        "category": "Server & Storage",
        "items": [{"raw_name": "Dell PowerEdge R750", "brand": "Dell"}],
    }

    res = generate_ai_recommendation(proc)
    assert res["engine"].startswith("SOFTY Procurement AI Advisor")
    assert "Aloqabank" in res["analysis"]
    assert "Smart Server" in res["competitor_weakness"]
    assert res["suggested_discount_percent"] == 5.0
    assert res["suggested_price"] == 237_500_000.0
    assert res["optimal_contact_days_before"] == 45
    assert len(res["action_plan"]) >= 4
    assert "SOFTY" in res["commercial_pitch"]


def test_get_recommendation_for_procedure() -> None:
    engine = create_engine("sqlite:///:memory:")
    tables = [
        Organization.__table__,
        Procedure.__table__,
        LotItem.__table__,
        Award.__table__,
        Classification.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)

    with Session(engine) as session:
        bank = Organization(name_canonical="Turonbank ATB", stir="200999888")
        supp = Organization(name_canonical="Tech Pro MCHJ", stir="309888777")
        session.add_all([bank, supp])
        session.flush()

        proc = Procedure(
            source="ebirja",
            source_id="eb_888",
            title="HP ProBook noutbuklari",
            customer_org_id=bank.id,
            start_price=Decimal("600000000"),
        )
        session.add(proc)
        session.flush()

        session.add(LotItem(procedure_id=proc.id, raw_name="HP ProBook 450 G10", brand="HP"))
        session.add(
            Award(procedure_id=proc.id, supplier_org_id=supp.id, amount=Decimal("590000000"))
        )
        session.commit()

        rec = get_recommendation_for_procedure(session, proc.id)
        assert "error" not in rec
        assert rec["suggested_discount_percent"] == 3.5
        assert rec["suggested_price"] == 569_350_000.0
        assert "Turonbank" in rec["analysis"]


def test_macro_business_strategy_expert_mode() -> None:
    from datetime import UTC, datetime

    from radar.ai_advisor import (
        compute_macro_metrics,
        format_macro_strategy,
        generate_macro_business_strategy,
    )
    from radar.models import RenewalOpportunity

    engine = create_engine("sqlite:///:memory:")
    tables = [
        Organization.__table__,
        Procedure.__table__,
        LotItem.__table__,
        Award.__table__,
        Classification.__table__,
        RenewalOpportunity.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)

    with Session(engine) as session:
        cust = Organization(name_canonical="Milliy Bank ATB", stir="200111333")
        supp = Organization(name_canonical="Smart IT Support MCHJ", stir="305222444")
        session.add_all([cust, supp])
        session.flush()

        proc = Procedure(
            source="uzex",
            source_id="uzex_999",
            title="Microsoft 365 litsenziyalari",
            customer_org_id=cust.id,
            start_price=Decimal("150000000"),
        )
        session.add(proc)
        session.flush()

        session.add(Classification(
            procedure_id=proc.id,
            is_it=True,
            category="Dasturiy ta'minot",
            brand="Microsoft",
            is_subscription=True,
            method="rule",
            confidence=0.9,
        ))
        session.add(Award(
            procedure_id=proc.id,
            supplier_org_id=supp.id,
            amount=Decimal("145000000"),
        ))
        session.add(RenewalOpportunity(
            procedure_id=proc.id,
            customer_org_id=cust.id,
            category="Dasturiy ta'minot",
            brand="Microsoft",
            lifecycle_months=12,
            score=95,
            amount=Decimal("150000000"),
            computed_at=datetime.now(UTC),
        ))
        session.commit()

        metrics = compute_macro_metrics(session)
        assert metrics["total_procedures"] == 1
        assert metrics["it_procedures"] == 1
        assert metrics["it_volume_uzs"] == 150_000_000.0
        assert metrics["hot_renewals"] == 1

        strategy = generate_macro_business_strategy(session, api_key=None)
        assert "SOFTY Strategic Business Advisor" in strategy["engine"]
        assert "Milliy Bank ATB" in strategy["executive_summary"]
        assert len(strategy["target_segments"]) >= 3

        report = format_macro_strategy(strategy)
        assert "SOFTY BIZNES STRATEGIYASI" in report
        assert "150,000,000 UZS" in report

