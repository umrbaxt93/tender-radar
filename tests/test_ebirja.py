"""Unit tests for E-IMZO authentication bridge and E-Birja adapter/importer."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from radar.eimzo import EImzoManager
from radar.models import (
    Award,
    Base,
    Classification,
    LotItem,
    Organization,
    OrganizationAlias,
    Procedure,
)
from radar.source.ebirja import (
    import_ebirja_records,
    parse_ebirja_auction,
    parse_ebirja_contract,
)


@pytest.fixture
def temp_session_file(tmp_path: Path) -> Path:
    return tmp_path / "eimzo_session.json"


@pytest.fixture
def memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    tables = [
        Organization.__table__,
        OrganizationAlias.__table__,
        Procedure.__table__,
        LotItem.__table__,
        Award.__table__,
        Classification.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session


def test_eimzo_manager_session_lifecycle(temp_session_file: Path) -> None:
    mgr = EImzoManager(session_file=temp_session_file)

    # Initial state
    sess = mgr.get_session()
    assert sess["authenticated"] is False
    assert sess["token"] is None

    # Save session
    saved = mgr.save_session(
        token="jwt_token_12345", tin="308904387", user_data={"name": "Umidjon"}
    )
    assert saved["authenticated"] is True
    assert saved["token"] == "jwt_token_12345"
    assert saved["tin"] == "308904387"

    # Read saved session
    read_sess = mgr.get_session()
    assert read_sess["authenticated"] is True
    assert read_sess["token"] == "jwt_token_12345"

    # Auth headers
    headers = mgr.get_auth_headers()
    assert headers["Authorization"] == "Bearer jwt_token_12345"
    assert headers["user-key"] == "jwt_token_12345"

    # Clear session
    mgr.clear_session()
    cleared = mgr.get_session()
    assert cleared["authenticated"] is False
    assert cleared["token"] is None


def test_parse_ebirja_contract() -> None:
    raw_contract = {
        "id": 31647,
        "number": "XD26029270",
        "created_at": "2026-09-14 18:21:02",
        "price": 4800000,
        "currency": "000",
        "customer": {"title": "O'zbekgidroenergo AJ", "tin": "200123456"},
        "producer": {"title": "Smart Server MCHJ", "tin": "305987654"},
        "position_count": 2,
        "order": {
            "lot_number": "26521008038274",
            "product_name": "Kaspersky Endpoint Security for Business",
        },
    }

    rec = parse_ebirja_contract(raw_contract, contract_type="Shop")
    assert rec.source_id == "ebirja_c_31647"
    assert "Kaspersky" in rec.title or "Kaspersky" in rec.items[0].raw_name
    assert rec.start_price == Decimal("4800000")
    assert rec.currency == "UZS"
    assert rec.customer_name == "O'zbekgidroenergo AJ"
    assert rec.customer_stir == "200123456"
    assert rec.award is not None
    assert rec.award.supplier_name == "Smart Server MCHJ"
    assert rec.award.supplier_stir == "305987654"
    assert rec.award.amount == Decimal("4800000")
    assert len(rec.items) == 1
    assert rec.items[0].quantity == Decimal("2")


def test_parse_ebirja_auction() -> None:
    raw_auction = {
        "id": 803,
        "lot": "26521007037107",
        "type": 1,
        "title": "Server uskunalari va tarmoq qurilmalari xaridi",
        "company": {"id": 897, "title": "RADIOALOQA UK", "tin": "200625403"},
        "begin_date": "2026-09-10 10:00:00",
        "auction_end": "2026-09-17 17:00:00",
        "position_count": 1,
        "total_sum": 150000000,
    }

    rec = parse_ebirja_auction(raw_auction)
    assert rec.source_id == "ebirja_a_803"
    assert rec.procedure_type == "E-Birja Auksion"
    assert rec.status == "ACTIVE"
    assert rec.start_price == Decimal("150000000")
    assert rec.customer_name == "RADIOALOQA UK"
    assert rec.customer_stir == "200625403"


def test_import_ebirja_records_idempotency(memory_session: Session) -> None:
    raw_contract = {
        "id": 999111,
        "number": "XD999111",
        "created_at": "2026-08-01 12:00:00",
        "price": 12500000,
        "currency": "000",
        "customer": {"title": "Xalq Banki ATB", "tin": "200222333"},
        "producer": {"title": "Kompyuter Servis XK", "tin": "300444555"},
        "position_count": 5,
        "order": {
            "lot_number": "26521009999",
            "product_name": "HP LaserJet Pro MFP 4103dw",
        },
    }

    rec = parse_ebirja_contract(raw_contract)

    # First import
    stats1 = import_ebirja_records(memory_session, [rec])
    assert stats1["inserted"] == 1
    assert stats1["updated"] == 0
    assert stats1["items"] == 1

    proc = memory_session.scalar(select(Procedure).where(Procedure.source_id == "ebirja_c_999111"))
    assert proc is not None
    assert proc.source == "ebirja"
    assert proc.customer is not None
    assert proc.customer.name_canonical == "Xalq Banki ATB"
    assert proc.award is not None
    assert proc.award.supplier.name_canonical == "Kompyuter Servis XK"
    assert len(proc.items) == 1
    assert proc.items[0].raw_name == "HP LaserJet Pro MFP 4103dw"
    assert proc.items[0].brand == "HP"

    # Second import (idempotent update, 0 duplicates)
    stats2 = import_ebirja_records(memory_session, [rec])
    assert stats2["inserted"] == 0
    assert stats2["updated"] == 1

    total_procs = memory_session.scalars(select(Procedure)).all()
    assert len(total_procs) == 1
