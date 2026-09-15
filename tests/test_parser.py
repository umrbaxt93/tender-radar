from datetime import UTC, datetime
from decimal import Decimal

from radar.source.parser import (
    parse_datetime,
    parse_decimal,
    parse_detail,
    parse_list_page,
)


def test_parse_list_page(samples_dir):
    total_lots = len(list(samples_dir.glob("detail_*.json")))
    page = parse_list_page((samples_dir / "list_page_1.json").read_bytes())
    assert page.total == total_lots
    assert len(page.entries) == min(total_lots, 50)
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
    assert rec.completed_at == datetime(2025, 10, 13, 23, 0, tzinfo=UTC)
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


def test_parse_real_uzex_samples():
    from pathlib import Path
    samples = Path(__file__).resolve().parents[1] / "samples" / "uzex"
    list_path = samples / "list_response.json"
    detail_path = samples / "detail_response.json"
    assert list_path.is_file(), "samples/uzex/list_response.json missing"
    assert detail_path.is_file(), "samples/uzex/detail_response.json missing"

    page = parse_list_page(list_path.read_bytes())
    assert page.total == 4710
    assert len(page.entries) == 10
    assert page.entries[0].source_id == "24197"
    assert page.entries[0].completed_at == datetime(2026, 9, 18, 18, 0, tzinfo=UTC)

    detail = parse_detail(detail_path.read_bytes())
    assert detail.source_id == "20000"
    assert detail.customer_stir == "206916313"
    assert detail.customer_name == "BIZNESNI RIVOJLANTIRISH BANKI AKSIYADORLIK TIJORAT BANKI"
    assert detail.start_price == Decimal("48000000.0")
    assert detail.currency == "UZS"
    assert len(detail.items) == 1
    exp_name = "Услуга экспертно-консультативная в области экономического развития"
    assert detail.items[0].raw_name == exp_name
    assert detail.award is not None
    assert detail.award.supplier_name == "Zayniddinov Nurali Sherali ou2018gu2018li"
    assert detail.award.supplier_stir == "111111111"
    assert detail.award.amount == Decimal("48000000.0")
    assert detail.award.awarded_at == datetime(2026, 2, 5, 14, 0, tzinfo=UTC)



def test_a_zero_date_sentinel_is_not_a_date():
    """UZEX returns 0001-01-01 to mean "no date". Taken literally it became a real
    timestamp that then fed renewal maths and the export."""
    assert parse_datetime("0001-01-01T00:00:00") is None
    assert parse_datetime("01.01.0001") is None
    assert parse_datetime("1899-12-31") is None
    assert parse_datetime("2024-01-04T10:00:00") == datetime(2024, 1, 4, 10, tzinfo=UTC)


def test_control_characters_are_stripped_from_every_record_string():
    """A UZEX organisation name arrived carrying NUL bytes. Postgres text columns reject
    those outright, so the whole import run died on one bad row."""
    from radar.source.parser import AwardRecord, LotItemRecord, ProcedureRecord

    proc = ProcedureRecord(source_id="x", title="Medaostach\x00 Group \x00LLC",
                           customer_name="A\x00B", customer_region="T\x1fosh")
    assert proc.title == "Medaostach Group LLC"
    assert proc.customer_name == "AB"
    assert proc.customer_region == "Tosh"
    assert AwardRecord(supplier_name="X\x00Y").supplier_name == "XY"
    assert LotItemRecord(raw_name="P\x00Q").raw_name == "PQ"
    # Ordinary text, including newlines and non-Latin scripts, is untouched.
    keeps = ProcedureRecord(source_id="y", title="Сервер\nHP ProLiant")
    assert keeps.title == "Сервер\nHP ProLiant"
