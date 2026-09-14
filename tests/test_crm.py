"""Unit tests for Bitrix24 CRM module (radar.crm).

Tests cover:
- get_company_profile_and_timeline
- generate_grounded_proposal
- push_deal_for_procedure with strict idempotency (no duplicate deals)
- push_to_bitrix24 wrapper
- create_sales_task and assign_staff
- Live or mocked Bitrix24 HTTP call handling
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from radar.crm import (
    assign_staff,
    call_bitrix_api,
    create_sales_task,
    generate_grounded_proposal,
    get_company_profile_and_timeline,
    push_deal_for_procedure,
    push_to_bitrix24,
)
from radar.models import Award, CrmDeal, CrmTask, LotItem, Organization, Procedure


@pytest.fixture
def crm_sample_data(session):
    """Seed sample organization, procedures, items, and award in test DB."""
    org = Organization(
        stir="123456789",
        name_canonical="OOO Test Enterprise",
        region="Toshkent shahri",
    )
    session.add(org)
    session.flush()

    supplier = Organization(
        stir="987654321",
        name_canonical="OOO Tech Vendor",
        region="Toshkent",
    )
    session.add(supplier)
    session.flush()

    proc1 = Procedure(
        source="xt_xarid",
        source_id="TEST-101",
        source_url="https://xt-xarid.uz/contract/TEST-101",
        customer_org_id=org.id,
        title="Kaspersky Endpoint Security litsenziyasi 1 yil",
        start_price=Decimal("15000000.00"),
        status="COMPLETED",
        currency="UZS",
        published_at=datetime(2025, 6, 1, 10, 0, tzinfo=UTC),
        completed_at=datetime(2025, 6, 15, 10, 0, tzinfo=UTC),
    )
    session.add(proc1)
    session.flush()

    item1 = LotItem(
        procedure_id=proc1.id,
        raw_name="Kaspersky Endpoint Security for Business 100 node 1 yil",
        brand="Kaspersky",
        product_family="Endpoint Security",
        model=None,
        term_months=12,
        quantity=Decimal("1.000"),
        unit="dona",
        unit_price_raw="15000000.00",
    )
    session.add(item1)

    award1 = Award(
        procedure_id=proc1.id,
        supplier_org_id=supplier.id,
        amount=Decimal("14500000.00"),
        awarded_at=datetime(2025, 6, 15, 10, 0, tzinfo=UTC),
    )
    session.add(award1)

    proc2 = Procedure(
        source="uzex",
        source_id="TEST-202",
        source_url="https://xarid.uzex.uz/lot/TEST-202",
        customer_org_id=org.id,
        title="AutoCAD LT 2026 yangilash",
        start_price=Decimal("30000000.00"),
        status="ANN",
        currency="UZS",
        published_at=datetime(2025, 8, 1, 10, 0, tzinfo=UTC),
    )
    session.add(proc2)
    session.flush()

    item2 = LotItem(
        procedure_id=proc2.id,
        raw_name="AutoCAD LT 2026; 1 yil",
        brand="Autodesk",
        product_family="AutoCAD LT",
        model=None,
        term_months=12,
        quantity=Decimal("2.000"),
        unit="dona",
        unit_price_raw="15000000.00",
    )
    session.add(item2)
    session.commit()

    return {"org": org, "proc1": proc1, "proc2": proc2, "supplier": supplier}


def test_timeline_nonexistent_stir(session):
    data = get_company_profile_and_timeline(session, "000000000")
    assert data["found"] is False


def test_timeline_existing_company(session, crm_sample_data):
    org = crm_sample_data["org"]
    data = get_company_profile_and_timeline(session, org.stir)

    assert data["found"] is True
    assert data["company"]["stir"] == "123456789"
    assert data["company"]["calculated_proof_status"] == "VERIFIED_BUYER"
    assert data["total_procedures"] == 2

    # Check first procedure (proc1, completed)
    event1 = next(e for e in data["timeline"] if e["source_id"] == "TEST-101")
    assert event1["is_verified_contract"] is True
    assert event1["supplier_name"] == "OOO Tech Vendor"
    assert len(event1["items"]) == 1
    assert event1["items"][0]["brand"] == "Kaspersky"
    assert event1["items"][0]["term_months"] == 12


def test_grounded_proposal_structure(session, crm_sample_data):
    org = crm_sample_data["org"]
    prop = generate_grounded_proposal(session, org.stir)

    assert prop["company_name"] == "OOO Test Enterprise"
    assert prop["stir"] == "123456789"
    assert prop["status"] == "DRAFT_REQUIRES_HUMAN_CONFIRMATION"
    assert prop["auto_send_allowed"] is False
    assert "To'qima narxlar kiritilmagan" in prop["pricing_notice"]
    assert len(prop["observed_products"]) >= 1


def test_push_deal_for_procedure_strict_idempotency(session, crm_sample_data):
    proc1 = crm_sample_data["proc1"]

    # 1. First creation
    res1 = push_deal_for_procedure(
        session=session,
        procedure_id=proc1.id,
        use_mock=True,
    )
    assert res1["status"] == "created"
    assert res1["created"] is True
    deal_id = res1["deal_id"]
    assert deal_id == "BX24-xt_xarid-TEST-101"

    # Verify CrmDeal and CrmTask exist in database
    deal = session.execute(
        select(CrmDeal).where(CrmDeal.procedure_id == proc1.id)
    ).scalar_one()
    assert deal.deal_id == deal_id
    assert deal.amount == Decimal("14500000.00")

    task = session.execute(
        select(CrmTask).where(CrmTask.procedure_id == proc1.id)
    ).scalar_one()
    assert task.bitrix_deal_id == deal_id
    assert task.status == "BAJARILDI"

    # 2. Second call with SAME procedure_id — MUST BE IDEMPOTENT (no duplicate)
    res2 = push_deal_for_procedure(
        session=session,
        procedure_id=proc1.id,
        use_mock=True,
    )
    assert res2["status"] == "already_exists"
    assert res2["created"] is False
    assert res2["deal_id"] == deal_id

    # Verify only 1 row exists in crm_deal for this procedure_id
    deals_count = len(
        session.execute(
            select(CrmDeal).where(CrmDeal.procedure_id == proc1.id)
        ).scalars().all()
    )
    assert deals_count == 1


def test_push_to_bitrix24_by_stir(session, crm_sample_data):
    org = crm_sample_data["org"]

    # Call with STIR
    res = push_to_bitrix24(session, target=org.stir, use_mock=True)
    assert res["success"] is True
    assert res["bitrix_deal_id"] is not None

    # Calling again with STIR must return already_existed=True
    res_repeat = push_to_bitrix24(session, target=org.stir, use_mock=True)
    assert res_repeat["success"] is True
    assert res_repeat["already_existed"] is True
    assert res_repeat["bitrix_deal_id"] == res["bitrix_deal_id"]


def test_sales_task_and_assign_staff(session, crm_sample_data):
    org = crm_sample_data["org"]

    task_res = create_sales_task(
        session=session,
        inn=org.stir,
        task_title="Maxsus taklif tayyorlash",
        assigned_staff_id="usmon",
    )
    assert task_res["success"] is True
    assert task_res["assigned_to"] == "Usmon"

    assign_res = assign_staff(session, org.stir, "yoqubxon")
    assert assign_res["success"] is True
    assert assign_res["assigned_staff_name"] == "Yoqubxon"


def test_web_api_crm_endpoints(session, engine, monkeypatch, crm_sample_data):
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    from radar import web

    @contextmanager
    def scope(*args, **kwargs):
        yield session

    monkeypatch.setattr(web, "session_scope", scope)
    monkeypatch.setattr(web, "get_engine", lambda *a, **k: engine)

    client = TestClient(web.app)
    org = crm_sample_data["org"]
    proc = crm_sample_data["proc1"]

    # 1. Timeline endpoint
    t_res = client.get(f"/api/companies/{org.stir}/timeline")
    assert t_res.status_code == 200
    assert t_res.json()["found"] is True

    # 2. Proposal endpoint
    p_res = client.get(f"/api/companies/{org.stir}/proposal")
    assert p_res.status_code == 200
    assert p_res.json()["stir"] == org.stir

    # 3. Bitrix deal endpoint (mock mode)
    b_res = client.post(f"/api/procedures/{proc.id}/bitrix", json={"mock": True})
    assert b_res.status_code == 200
    assert b_res.json()["status"] in ("created", "already_exists")


def test_call_bitrix_api_mocked():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"result": 999}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = call_bitrix_api(
            method="crm.deal.add",
            params={"fields": {"TITLE": "Test Deal"}},
            webhook_url="https://test.bitrix24.uz/rest/1/abc/",
        )
        assert res == 999
