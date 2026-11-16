"""cooperation.uz purchase plans: parsing and idempotent import (SQLite in memory)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from radar.models import (
    Award,
    Base,
    Classification,
    LotItem,
    Organization,
    OrganizationAlias,
    Procedure,
)
from radar.source.cooperation import (
    import_cooperation,
    load_cooperation_json,
    parse_cooperation_row,
)

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "cooperation" / "plans_sample.json"


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


def test_parse_row_is_a_plan_not_a_contract() -> None:
    row = json.loads(SAMPLE.read_text(encoding="utf-8"))[0]
    rec = parse_cooperation_row(row)
    assert rec is not None
    assert rec.source_id == row["id"]
    assert rec.status == "PLANNED"
    assert rec.completed_at is None and rec.award is None
    assert rec.start_price is None  # 0.0 in the scrape means "no price"
    assert rec.customer_region is None  # scrape "region" is the plan quarter
    assert rec.items and rec.items[0].quantity == Decimal("23.8") and rec.items[0].unit == "dona"


def test_parse_row_rejects_empty() -> None:
    assert parse_cooperation_row({"id": "", "title": "x"}) is None
    assert parse_cooperation_row({"id": "coop_1", "title": ""}) is None


def test_import_is_idempotent_and_classifies(memory_session: Session) -> None:
    records = load_cooperation_json(SAMPLE)
    assert len(records) == 5
    first = import_cooperation(memory_session, records)
    assert first["inserted"] == 5 and first["updated"] == 0
    second = import_cooperation(memory_session, records)
    assert second["inserted"] == 0 and second["updated"] == 5
    procs = list(memory_session.scalars(select(Procedure)))
    assert len(procs) == 5
    assert {p.source for p in procs} == {"cooperation"}
    assert all(p.completed_at is None for p in procs)
    assert memory_session.scalar(select(Award)) is None
    assert len(list(memory_session.scalars(select(Classification)))) == 5
