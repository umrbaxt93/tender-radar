from datetime import UTC, datetime
from decimal import Decimal

from radar.source.parser import (
    parse_datetime,
    parse_decimal,
    parse_detail,
    parse_list_page,
)


def test_parse_list_page(samples_dir):
    page = parse_list_page((samples_dir / "list_page_1.json").read_bytes())
    assert page.total == 12
    assert len(page.entries) == 12
    assert all(e.source_id.startswith("SYN-") for e in page.entries)
    assert page.entries[0].completed_at is not None
    # listing is newest first
    dates = [e.completed_at for e in page.entries]
    assert dates == sorted(dates, reverse=True)


def test_parse_detail(samples_dir):
    rec = parse_detail((samples_dir / "detail_SYN-000001.json").read_bytes())
    assert rec.source_id == "SYN-000001"
    assert rec.source_url and rec.source_url.endswith("SYN-000001")
    assert rec.customer_stir == "900000006"
    assert "SYNTHETIC" in (rec.customer_name or "")
    assert rec.completed_at == datetime(2025, 10, 1, 23, 0, tzinfo=UTC)
    assert rec.start_price == Decimal("240000000")
    assert len(rec.items) == 1 and rec.items[0].quantity == Decimal("5")
    assert rec.award is None


def test_parse_detail_with_award(samples_dir):
    import json
    found = None
    for path in sorted(samples_dir.glob("detail_*.json")):
        if "award" in json.loads(path.read_text()):
            found = parse_detail(path.read_bytes())
            break
    assert found is not None and found.award is not None
    assert found.award.amount is not None and found.award.supplier_name


def test_datetime_and_decimal_parsing():
    assert parse_datetime("2025-01-05T10:00:00Z") == datetime(2025, 1, 5, 10, tzinfo=UTC)
    assert parse_datetime("05.01.2025 10:00") == datetime(2025, 1, 5, 10, tzinfo=UTC)
    assert parse_datetime("2025-01-05") == datetime(2025, 1, 5, tzinfo=UTC)
    assert parse_datetime(1736071200000) == datetime(2025, 1, 5, 10, tzinfo=UTC)
    assert parse_datetime("") is None and parse_datetime("garbage") is None
    assert parse_decimal("1 250 000,50 сум") == Decimal("1250000.50")
    assert parse_decimal("1,250,000.50") == Decimal("1250000.50")
    assert parse_decimal(12) == Decimal("12")
    assert parse_decimal("") is None and parse_decimal(True) is None


def test_missing_id_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        parse_detail({"title": "no id"})
