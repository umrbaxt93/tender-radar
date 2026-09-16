"""Unit tests for SQLite to PostgreSQL historical migration."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from radar.migration import migrate_all_sqlite
from radar.models import (
    Award,
    Base,
    Classification,
    LotItem,
    Organization,
    OrganizationAlias,
    Procedure,
)


def _setup_sqlite(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE companies (
            inn TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            legal_address TEXT,
            region TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE lots (
            id TEXT PRIMARY KEY,
            lot_number TEXT,
            title TEXT NOT NULL,
            description TEXT,
            platform_id TEXT,
            source_url TEXT,
            procurement_type TEXT,
            official_status TEXT,
            announcement_date TEXT,
            deadline_date TEXT,
            result_date TEXT,
            contract_date TEXT,
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
            id INTEGER PRIMARY KEY,
            lot_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            brand TEXT,
            product_family TEXT,
            quantity REAL,
            unit TEXT,
            unit_price REAL,
            total_price REAL
        );
    """)

    # Seed 1 company, 1 lot, 1 item
    cur.execute(
        "INSERT INTO companies VALUES (?, ?, ?, ?, ?, ?)",
        (
            "200333444",
            "O'zbekiston Milliy Universiteti",
            "998711112233",
            "info@nuu.uz",
            "Toshkent",
            "Olmazor",
        ),
    )
    cur.execute(
        "INSERT INTO lots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "uzex_1001",
            "1001",
            "Kaspersky Endpoint Security litsenziyalari",
            "1 yillik litsenziya",
            "uzex",
            "https://xarid.uzex.uz/purchase/detail/1001",
            "Auksion",
            "COMPLETED",
            "2025-05-10",
            "2025-05-20",
            "2025-05-21",
            "2025-05-22",
            50000000.0,
            48500000.0,
            "UZS",
            "200333444",
            "O'zbekiston Milliy Universiteti",
            "305999000",
            "Soft Tech Savdo MCHJ",
            "Soft Tech Savdo MCHJ",
            "Toshkent",
        ),
    )
    cur.execute(
        "INSERT INTO contract_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "uzex_1001",
            "Kaspersky Endpoint Security Cloud",
            "Kaspersky",
            "Endpoint Security",
            100.0,
            "dona",
            485000.0,
            48500000.0,
        ),
    )
    conn.commit()
    conn.close()


def test_migrate_all_sqlite(tmp_path: Path) -> None:
    sqlite_file = tmp_path / "test_proc.db"
    _setup_sqlite(sqlite_file)

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
        # First migration run
        stats1 = migrate_all_sqlite(session, sqlite_path=sqlite_file)
        assert stats1["companies_synced"] == 1
        assert stats1["lots_considered"] == 1
        assert stats1["procedures_inserted"] == 1
        assert stats1["items_migrated"] == 1
        assert stats1["awards_migrated"] == 1
        assert stats1["classifications_migrated"] == 1

        # Check procedure in database
        proc = session.query(Procedure).filter_by(source="uzex", source_id="1001").first()
        assert proc is not None
        assert proc.start_price == Decimal("48500000")
        assert proc.customer is not None
        assert proc.customer.stir == "200333444"

        # Check lot items
        assert len(proc.items) == 1
        assert proc.items[0].brand == "Kaspersky"

        # Check classification
        assert proc.classification is not None
        assert proc.classification.is_it is True
        assert proc.classification.brand == "Kaspersky"

        # Check idempotency on second run
        stats2 = migrate_all_sqlite(session, sqlite_path=sqlite_file)
        assert stats2["procedures_inserted"] == 0
        assert stats2["procedures_updated"] == 1
