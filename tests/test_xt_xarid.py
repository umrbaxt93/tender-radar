"""Tests for XT-Xarid mapping, parser, and migration."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from sqlalchemy import select

from radar.migrate_xt import migrate_xt_lots
from radar.models import Procedure
from radar.source.parser import load_mapping, parse_detail


def test_xt_xarid_mapping_loads():
    mapping = load_mapping("xt_xarid")
    assert mapping["list"]["id_field"] == "lot_id"
    assert mapping["detail"]["currency"] == "currency"
    assert "xt-xarid.uz" in mapping["detail"]["source_url_template"]


def test_parse_xt_xarid_list_page():
    from pathlib import Path

    from radar.source.parser import parse_list_page

    mapping = load_mapping("xt_xarid")
    sample = Path(__file__).resolve().parents[1] / "samples" / "xt_xarid" / "list_page_1.json"
    if sample.is_file():
        page = parse_list_page(sample.read_bytes(), mapping=mapping)
        assert page.total == 5
        assert len(page.entries) == 5
        assert page.entries[0].source_id is not None



def test_parse_xt_xarid_detail():
    mapping = load_mapping("xt_xarid")
    raw = {
        "lot_id": "6471358",
        "lot_number": "6471358",
        "title": "AutoCAD LT 2026; 1 yil",
        "description": "AutoCAD LT 2026; 1 yil",
        "procurement_type": "Elektron do‘kon",
        "status": "COMPLETED",
        "announcement_date": "2026-01-20",
        "contract_date": "2026-01-20",
        "deadline_date": None,
        "start_price": 34777588.0,
        "final_price": 34777588.0,
        "currency": "UZS",
        "buyer_name": "TOSHKENT XALQARO AEROPORTI",
        "buyer_inn": "200640719",
        "region": "Сергелийский район",
        "winner_name": "ИП ООО NOVENTIQ",
        "supplier_name": "ИП ООО NOVENTIQ",
        "supplier_inn": None,
        "items": [
            {
                "product_name": "AutoCAD LT 2026; 1 yil",
                "quantity": 1.0,
                "unit": "dona",
                "unit_price": 34777588.0,
            }
        ]
    }
    rec = parse_detail(raw, mapping=mapping)
    assert rec.source_id == "6471358"
    assert rec.title == "AutoCAD LT 2026; 1 yil"
    assert rec.customer_name == "TOSHKENT XALQARO AEROPORTI"
    assert rec.customer_stir == "200640719"
    assert rec.start_price == Decimal("34777588.0")
    assert len(rec.items) == 1
    assert rec.items[0].raw_name == "AutoCAD LT 2026; 1 yil"
    assert rec.award is not None
    assert rec.award.supplier_name == "ИП ООО NOVENTIQ"
    assert rec.award.amount == Decimal("34777588.0")


def test_migrate_xt_lots_only_imports_real_xt_records(session, tmp_path):
    # Setup temporary SQLite db mimicking softy_procurement.db
    sqlite_file = tmp_path / "test_procurement.db"
    conn = sqlite3.connect(sqlite_file)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE lots (
            id TEXT PRIMARY KEY,
            lot_number TEXT,
            title TEXT,
            description TEXT,
            platform_id TEXT,
            source_url TEXT,
            procurement_type TEXT,
            official_status TEXT,
            announcement_date TEXT,
            deadline_date TEXT,
            contract_date TEXT,
            license_end_date TEXT,
            start_price REAL,
            final_price REAL,
            currency TEXT,
            buyer_inn TEXT,
            buyer_name TEXT,
            supplier_inn TEXT,
            supplier_name TEXT,
            winner_name TEXT,
            region TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE contract_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lot_id TEXT,
            product_name TEXT,
            brand TEXT,
            product_family TEXT,
            quantity REAL,
            unit TEXT,
            unit_price REAL,
            total_price REAL
        );
    """)

    # 1 Real xt_* lot
    cur.execute("""
        INSERT INTO lots (
            id, lot_number, title, platform_id, official_status, announcement_date,
            contract_date, start_price, final_price, currency, buyer_inn, buyer_name,
            winner_name, supplier_name, region
        ) VALUES (
            'xt_12345', '12345', 'Zoom Video Webinars 1 yil', 'xt_xarid', 'COMPLETED',
            '2025-05-10', '2025-05-10', 15000000.0, 15000000.0, 'UZS', '123456789',
            'Test Buyurtmachi AJ', 'Test Winner MCHJ', 'Test Winner MCHJ', 'Toshkent'
        );
    """)
    cur.execute("""
        INSERT INTO contract_items (
            lot_id, product_name, brand, product_family, quantity, unit, unit_price, total_price
        ) VALUES ('xt_12345', 'Zoom Video Webinars', 'Zoom', 'Zoom Video', 1.0,
                  'dona', 15000000.0, 15000000.0);
    """)

    # 1 Synthetic lot that MUST BE IGNORED
    cur.execute("""
        INSERT INTO lots (
            id, lot_number, title, platform_id, official_status, announcement_date,
            contract_date, start_price, final_price, currency, buyer_inn, buyer_name
        ) VALUES (
            'uzex_kasp_9999', '9999', 'Synthetic Kaspersky', 'uzex', 'COMPLETED',
            '2025-01-01', '2025-01-01', 5000000.0, 5000000.0, 'UZS', '999999999', 'Fake Org'
        );
    """)
    conn.commit()
    conn.close()

    stats = migrate_xt_lots(session, sqlite_path=sqlite_file)
    assert stats["considered"] == 1  # Only the xt_* lot considered!
    assert stats["inserted"] == 1

    stmt = select(Procedure).where(
        Procedure.source == "xt_xarid", Procedure.source_id == "12345"
    )
    proc = session.scalar(stmt)
    assert proc is not None
    assert proc.title == "Zoom Video Webinars 1 yil"
    assert proc.customer.name_canonical == "Test Buyurtmachi AJ"
    assert proc.award.supplier.name_canonical == "Test Winner MCHJ"
    assert proc.award.amount == Decimal("15000000.00")

    # Synthetic lot must NOT exist
    assert session.scalar(select(Procedure).where(Procedure.source_id == "9999")) is None
