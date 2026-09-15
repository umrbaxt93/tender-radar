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
