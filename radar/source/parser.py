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
from pydantic import BaseModel, Field, field_validator

MAPPING_PATH = Path(__file__).with_name("uzex_mapping.yaml")

# Source strings land in Postgres text columns, which reject NUL outright. One UZEX
# organisation name arrived as "Medaostach\x00 Group \x00LLC" and killed an entire
# import run, so every string is scrubbed as it enters a record.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SourceRecord(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip_control_chars(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _CONTROL_CHARS.sub("", value)
        return value


class LotItemRecord(SourceRecord):
    raw_name: str
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price_raw: str | None = None


class AwardRecord(SourceRecord):
    supplier_name: str | None = None
    supplier_stir: str | None = None
    amount: Decimal | None = None
    awarded_at: datetime | None = None


class ProcedureRecord(SourceRecord):
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


@lru_cache(maxsize=4)
def load_mapping(path: str | Path = MAPPING_PATH) -> dict[str, Any]:
    if isinstance(path, str):
        if not path.endswith(".yaml") and not path.endswith(".yml") and "/" not in path:
            p = Path(__file__).with_name(f"{path}_mapping.yaml")
        else:
            p = Path(path)
    else:
        p = path
    with open(p, encoding="utf-8") as fh:
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


# UZEX returns 0001-01-01 where it means "no date". Parsed literally it becomes a real
# timestamp two millennia old, which then flows into renewal dates and the export.
_EARLIEST_PLAUSIBLE = datetime(1990, 1, 1, tzinfo=UTC)


def _aware(dt: datetime) -> datetime | None:
    dt = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return dt if dt >= _EARLIEST_PLAUSIBLE else None


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _aware(value)
    if isinstance(value, int | float):
        # epoch seconds or milliseconds
        ts = float(value) / (1000.0 if value > 10_000_000_000 else 1.0)
        return _aware(datetime.fromtimestamp(ts, tz=UTC))
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return _aware(datetime.fromisoformat(text))
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return _aware(datetime.strptime(text, fmt))
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
    items_path = spec.get("items_path")
    if isinstance(data, list):
        raw_items = data
    elif items_path:
        raw_items = dig(data, items_path) or []
    else:
        raw_items = dig(data, "data.items") or []
    if not isinstance(raw_items, list):
        raise ValueError(f"list items at {spec.get('items_path')!r} is not an array")
    entries = []
    for item in raw_items:
        sid = _str(dig(item, spec["id_field"]))
        completed_raw = dig(item, spec.get("completed_at_field")) or dig(item, "completed_at")
        completed = parse_datetime(completed_raw)
        entries.append(ListEntry(source_id=sid, completed_at=completed))
    total = dig(data, spec.get("total_path"))
    if total is None and isinstance(data, dict):
        total = dig(data, "data.total")
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
    raw_items = dig(data, ispec.get("path")) if ispec.get("path") else None
    if raw_items is None:
        raw_items = dig(data, "items") or []
    for raw in raw_items:
        name = _str(dig(raw, ispec.get("name"))) or _str(dig(raw, "name"))
        if not name:
            continue
        qty_val = dig(raw, ispec.get("quantity")) if ispec.get("quantity") else dig(raw, "quantity")
        unit_val = dig(raw, ispec.get("unit")) if ispec.get("unit") else dig(raw, "unit")
        price_val = (
            dig(raw, ispec.get("unit_price"))
            if ispec.get("unit_price")
            else dig(raw, "unit_price")
        )
        items.append(LotItemRecord(
            raw_name=name,
            quantity=parse_decimal(qty_val),
            unit=_str(unit_val),
            unit_price_raw=_str(price_val),
        ))
    award = None
    aspec = spec.get("award") or {}
    path = aspec.get("path")
    if path == "":
        raw_award = data
    elif path:
        raw_award = dig(data, path) or dig(data, "award")
    else:
        raw_award = dig(data, "award")
    if isinstance(raw_award, dict):
        amount = parse_decimal(dig(raw_award, aspec.get("amount"))) or parse_decimal(
            dig(raw_award, "amount")
        )
        if amount is None and aspec.get("amount_fallback"):
            amount = parse_decimal(dig(data, aspec["amount_fallback"]))
        awarded_at = parse_datetime(dig(raw_award, aspec.get("awarded_at"))) or parse_datetime(
            dig(raw_award, "awarded_at")
        )
        if awarded_at is None and aspec.get("awarded_at_fallback"):
            awarded_at = parse_datetime(dig(data, aspec["awarded_at_fallback"]))
        supp_name = (
            _str(dig(raw_award, aspec.get("supplier_name")))
            or _str(dig(raw_award, "supplier.name"))
            or _str(dig(raw_award, "supplier_name"))
        )
        supp_stir = (
            _str(dig(raw_award, aspec.get("supplier_stir")))
            or _str(dig(raw_award, "supplier.stir"))
            or _str(dig(raw_award, "supplier_stir"))
        )
        if supp_name or supp_stir or amount is not None:
            award = AwardRecord(
                supplier_name=supp_name,
                supplier_stir=supp_stir,
                amount=amount,
                awarded_at=awarded_at,
            )
    cspec = spec.get("customer") or {}
    template = spec.get("source_url_template")
    src_url = template.format(source_id=source_id) if template else _str(dig(data, "source_url"))
    proc_type = _str(dig(data, spec.get("procedure_type"))) or _str(dig(data, "procedure_type"))
    title = _str(dig(data, spec.get("title"))) or _str(dig(data, "title")) or ""
    status = _str(dig(data, spec.get("status"))) or _str(dig(data, "status"))
    pub_at = (
        parse_datetime(dig(data, spec.get("published_at")))
        or parse_datetime(dig(data, "published_at"))
    )
    dead_at = (
        parse_datetime(dig(data, spec.get("deadline_at")))
        or parse_datetime(dig(data, "deadline_at"))
    )
    comp_at = (
        parse_datetime(dig(data, spec.get("completed_at")))
        or parse_datetime(dig(data, "completed_at"))
    )
    curr = _str(dig(data, spec.get("currency"))) or _str(dig(data, "currency"))
    price = (
        parse_decimal(dig(data, spec.get("start_price")))
        or parse_decimal(dig(data, "start_price"))
    )
    cust_name = _str(dig(data, cspec.get("name"))) or _str(dig(data, "customer.name"))
    cust_stir = _str(dig(data, cspec.get("stir"))) or _str(dig(data, "customer.stir"))
    cust_region = _str(dig(data, cspec.get("region"))) or _str(dig(data, "customer.region"))
    return ProcedureRecord(
        source_id=source_id,
        source_url=src_url,
        procedure_type=proc_type,
        title=title,
        status=status,
        published_at=pub_at,
        deadline_at=dead_at,
        completed_at=comp_at,
        currency=curr,
        start_price=price,
        customer_name=cust_name,
        customer_stir=cust_stir,
        customer_region=cust_region,
        items=items,
        award=award,
    )
