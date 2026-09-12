"""Mapping-driven parser: raw source JSON -> normalized pydantic records.

The parser is deliberately data-driven (radar/source/uzex_mapping.yaml) because the
live endpoint contract is still UNVERIFIED. It is re-runnable from raw_snapshot rows.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

MAPPING_PATH = Path(__file__).with_name("uzex_mapping.yaml")


class LotItemRecord(BaseModel):
    raw_name: str
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price_raw: str | None = None


class AwardRecord(BaseModel):
    supplier_name: str | None = None
    supplier_stir: str | None = None
    amount: Decimal | None = None
    awarded_at: datetime | None = None


class ProcedureRecord(BaseModel):
    source_id: str
    source_url: str | None = None
    procedure_type: str | None = None
    title: str = ""
    status: str | None = None
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    completed_at: datetime | None = None
    currency: str | None = None
    start_price: Decimal | None = None
    customer_name: str | None = None
    customer_stir: str | None = None
    customer_region: str | None = None
    items: list[LotItemRecord] = Field(default_factory=list)
    award: AwardRecord | None = None


class ListEntry(BaseModel):
    source_id: str
    completed_at: datetime | None = None


class ListPage(BaseModel):
    entries: list[ListEntry]
    total: int | None = None


@lru_cache(maxsize=1)
def load_mapping(path: Path = MAPPING_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def dig(obj: Any, path: str | None) -> Any:
    """Follow a dotted path through dicts/lists; None when any step is missing."""
    if not path:
        return None
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if idx < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


_DATE_FORMATS = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
                 "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y")


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, int | float):
        # epoch seconds or milliseconds
        ts = float(value) / (1000.0 if value > 10_000_000_000 else 1.0)
        return datetime.fromtimestamp(ts, tz=UTC)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


_NUM_CLEAN = re.compile(r"[^0-9,.\-]")


def parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    text = _NUM_CLEAN.sub("", str(value))
    if text.count(",") and text.count("."):
        text = text.replace(",", "")
    elif text.count(",") == 1:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return Decimal(text) if text not in ("", "-", ".") else None
    except InvalidOperation:
        return None


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_list_page(body: bytes | str | dict, mapping: dict[str, Any] | None = None) -> ListPage:
    mapping = mapping or load_mapping()
    data = json.loads(body) if isinstance(body, bytes | str) else body
    spec = mapping["list"]
    raw_items = dig(data, spec["items_path"]) or []
    if not isinstance(raw_items, list):
        raise ValueError(f"list items at {spec['items_path']!r} is not an array")
    entries = []
    for item in raw_items:
        sid = _str(dig(item, spec["id_field"]))
        if not sid:
            continue
        completed = parse_datetime(dig(item, spec.get("completed_at_field")))
        entries.append(ListEntry(source_id=sid, completed_at=completed))
    total = dig(data, spec.get("total_path"))
    return ListPage(entries=entries, total=int(total) if isinstance(total, int | float) else None)


def parse_detail(body: bytes | str | dict,
                 mapping: dict[str, Any] | None = None) -> ProcedureRecord:
    mapping = mapping or load_mapping()
    data = json.loads(body) if isinstance(body, bytes | str) else body
    spec = mapping["detail"]
    source_id = _str(dig(data, spec["id"]))
    if not source_id:
        raise ValueError("detail response has no source id")
    items: list[LotItemRecord] = []
    ispec = spec.get("items") or {}
    for raw in dig(data, ispec.get("path")) or []:
        name = _str(dig(raw, ispec.get("name")))
        if not name:
            continue
        items.append(LotItemRecord(
            raw_name=name,
            quantity=parse_decimal(dig(raw, ispec.get("quantity"))),
            unit=_str(dig(raw, ispec.get("unit"))),
            unit_price_raw=_str(dig(raw, ispec.get("unit_price"))),
        ))
    award = None
    aspec = spec.get("award") or {}
    raw_award = dig(data, aspec.get("path")) if aspec else None
    if isinstance(raw_award, dict):
        award = AwardRecord(
            supplier_name=_str(dig(raw_award, aspec.get("supplier_name"))),
            supplier_stir=_str(dig(raw_award, aspec.get("supplier_stir"))),
            amount=parse_decimal(dig(raw_award, aspec.get("amount"))),
            awarded_at=parse_datetime(dig(raw_award, aspec.get("awarded_at"))),
        )
    cspec = spec.get("customer") or {}
    template = spec.get("source_url_template")
    return ProcedureRecord(
        source_id=source_id,
        source_url=template.format(source_id=source_id) if template else None,
        procedure_type=_str(dig(data, spec.get("procedure_type"))),
        title=_str(dig(data, spec.get("title"))) or "",
        status=_str(dig(data, spec.get("status"))),
        published_at=parse_datetime(dig(data, spec.get("published_at"))),
        deadline_at=parse_datetime(dig(data, spec.get("deadline_at"))),
        completed_at=parse_datetime(dig(data, spec.get("completed_at"))),
        currency=_str(dig(data, spec.get("currency"))),
        start_price=parse_decimal(dig(data, spec.get("start_price"))),
        customer_name=_str(dig(data, cspec.get("name"))),
        customer_stir=_str(dig(data, cspec.get("stir"))),
        customer_region=_str(dig(data, cspec.get("region"))),
        items=items,
        award=award,
    )
