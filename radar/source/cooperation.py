"""cooperation.uz purchase plans -> Tender Radar.

cooperation.uz blocks foreign and datacenter IPs, so the page scrape runs on the owner's Mac
(`~/.gemini/antigravity/scripts/cooperation/run_cooperation_sync.py`, weekly launchd job) and
writes one JSON file. This module imports that file; it never touches the network.

These rows are purchase *plans* (future demand), not completed contracts: they are stored with
status PLANNED, no completion date and no award, so they never enter the renewal radar or the
awarded-contract export, but they are classified and searchable as leads.
"""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from radar.source.ebirja import import_ebirja_records
from radar.source.parser import LotItemRecord, ProcedureRecord, parse_datetime

SOURCE = "cooperation"
DEFAULT_JSON_PATH = "~/.gemini/antigravity/scripts/cooperation/cooperation_latest.json"
_QTY_RE = re.compile(r"^\s*([\d\s]+(?:[.,]\d+)?)\s*(.*)$")


def json_path() -> Path:
    return Path(os.path.expanduser(os.environ.get("COOPERATION_JSON_PATH") or DEFAULT_JSON_PATH))


def _parse_volume(volume: str | None) -> tuple[Decimal | None, str | None]:
    """'19 litr' -> (19, 'litr'); anything unparseable -> (None, original text)."""
    if not volume:
        return None, None
    m = _QTY_RE.match(str(volume))
    if not m:
        return None, str(volume)[:64]
    try:
        qty = Decimal(m.group(1).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None, str(volume)[:64]
    unit = m.group(2).strip() or None
    return qty, (unit[:64] if unit else None)


def parse_cooperation_row(row: dict[str, Any]) -> ProcedureRecord | None:
    """Map one row written by scrape_cooperation.py to a ProcedureRecord (None if unusable)."""
    source_id = str(row.get("id") or "").strip()
    title = str(row.get("title") or "").strip()
    if not source_id or not title:
        return None
    raw: dict[str, Any] = {}
    try:
        raw = json.loads(row.get("raw_data_json") or "{}")
    except (TypeError, ValueError):
        raw = {}
    qty, unit = _parse_volume(raw.get("hajm"))
    item_name = str(row.get("description") or title).strip()[:1000] or title
    return ProcedureRecord(
        source_id=source_id[:64],
        source_url=row.get("source_url"),
        procedure_type=row.get("procurement_type") or "Xarid rejasi",
        title=title[:500],
        status="PLANNED",
        published_at=parse_datetime(row.get("announcement_date")),
        deadline_at=None,
        completed_at=None,
        currency=row.get("currency") or "UZS",
        start_price=None,  # plans carry no price; 0.0 in the scrape means "unknown"
        customer_name=(row.get("buyer_name") or None),
        customer_stir=(row.get("buyer_inn") or None),
        customer_region=None,  # the scrape's "region" column is the plan quarter, not a region
        items=[LotItemRecord(raw_name=item_name, quantity=qty, unit=unit)],
        award=None,
    )


def load_cooperation_json(path: Path | str | None = None) -> list[ProcedureRecord]:
    p = Path(path) if path else json_path()
    rows = json.loads(p.read_text(encoding="utf-8"))
    records: list[ProcedureRecord] = []
    seen: set[str] = set()
    for row in rows:
        rec = parse_cooperation_row(row)
        if rec and rec.source_id not in seen:
            seen.add(rec.source_id)
            records.append(rec)
    return records


def import_cooperation(session: Session, records: list[ProcedureRecord]) -> dict[str, int]:
    """Idempotent upsert keyed on (source='cooperation', source_id)."""
    return import_ebirja_records(session, records, source=SOURCE)
