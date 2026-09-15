"""Migration script for importing verified real XT-Xarid lots from SQLite."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from sqlalchemy.orm import Session

from radar.config import Settings, load_settings
from radar.importer import upsert_procedure
from radar.snapshots import store_snapshot
from radar.source.parser import load_mapping, parse_detail

log = logging.getLogger(__name__)

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[2] / "data" / "softy_procurement.db"


def migrate_xt_lots(session: Session, sqlite_path: Path | str | None = None,
                   settings: Settings | None = None) -> dict[str, int]:
    sqlite_path = Path(sqlite_path or DEFAULT_SQLITE_PATH)
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite database not found at {sqlite_path}")

    settings = settings or load_settings()
    mapping = load_mapping("xt_xarid")

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # CRITICAL: strictly filter ONLY real xt_* records, ignoring synthetic/seeded ones
    cur.execute(
        "SELECT * FROM lots WHERE id LIKE 'xt_%' ORDER BY id ASC;"
    )
    lot_rows = cur.fetchall()

    stats = {"considered": len(lot_rows), "inserted": 0, "updated": 0, "items": 0}

    for lot in lot_rows:
        lot_id_clean = str(lot["lot_number"] or lot["id"].replace("xt_", ""))

        # Get associated contract items
        cur.execute("SELECT * FROM contract_items WHERE lot_id = ?;", (lot["id"],))
        item_rows = cur.fetchall()

        items_payload = []
        for it in item_rows:
            items_payload.append({
                "product_name": it["product_name"] or lot["title"],
                "brand": it["brand"],
                "product_family": it["product_family"],
                "quantity": it["quantity"] or 1,
                "unit": it["unit"] or "dona",
                "unit_price": it["unit_price"] or it["total_price"],
                "total_price": it["total_price"] or it["unit_price"],
            })
            stats["items"] += 1

        if not items_payload:
            items_payload.append({
                "product_name": lot["title"],
                "quantity": 1,
                "unit": "dona",
                "unit_price": lot["final_price"],
                "total_price": lot["final_price"],
            })
            stats["items"] += 1

        source_url = lot["source_url"] or f"https://xt-xarid.uz/contract/{lot_id_clean}.1.1"

        raw_payload = {
            "lot_id": lot_id_clean,
            "lot_number": str(lot["lot_number"] or lot_id_clean),
            "title": lot["title"],
            "description": lot["description"] or lot["title"],
            "procurement_type": lot["procurement_type"] or "Elektron do‘kon",
            "status": lot["official_status"] or "COMPLETED",
            "announcement_date": lot["announcement_date"],
            "contract_date": lot["contract_date"] or lot["announcement_date"],
            "deadline_date": lot["deadline_date"],
            "license_end_date": lot["license_end_date"],
            "start_price": lot["start_price"] or lot["final_price"],
            "final_price": lot["final_price"],
            "currency": lot["currency"] or "UZS",
            "buyer_name": lot["buyer_name"],
            "buyer_inn": str(lot["buyer_inn"] or "").strip() or None,
            "region": lot["region"],
            "winner_name": lot["winner_name"] or lot["supplier_name"],
            "supplier_name": lot["supplier_name"] or lot["winner_name"],
            "supplier_inn": str(lot["supplier_inn"] or "").strip() or None,
            "items": items_payload,
        }

        raw_bytes = json.dumps(raw_payload, ensure_ascii=False).encode("utf-8")
        snap = store_snapshot(session, source_url, raw_bytes)
        rec = parse_detail(raw_bytes, mapping=mapping)

        _, created = upsert_procedure(
            session, rec, snap.id, source="xt_xarid",
            match_threshold=settings.org_match_threshold
        )
        if created:
            stats["inserted"] += 1
        else:
            stats["updated"] += 1

    session.commit()
    conn.close()
    return stats
