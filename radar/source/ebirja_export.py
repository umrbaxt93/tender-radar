"""E-Birja cabinet export files -> Tender Radar.

E-Birja's public contract endpoints stopped being a source in November 2026: one route was
withdrawn (404) and the other two now sit behind a CAPTCHA, which CLAUDE.md forbids working
around. CLAUDE.md also forbids logging in to ebirja.uz, and names cabinet export files as the
one authorised route to that data. So the owner downloads the export from the cabinet by hand
and this module reads the file; it never touches the network.

The export's real column headers were not available when this was written, so the layout lives
in `ebirja_export_mapping.yaml` as a list of candidate wordings per field, and
`describe_columns()` reports what a real file actually matched. Add the real wording to the YAML
rather than editing code.

Rows are grouped by contract number: a cabinet export normally gives one row per contract line
item, so several rows become one procedure with several line items.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from radar.source.ebirja import import_ebirja_records
from radar.source.parser import AwardRecord, LotItemRecord, ProcedureRecord, parse_datetime

# Export contracts take their own source name. The 32 489 rows imported from the API before it
# closed are keyed on E-Birja's internal numeric id (`ebirja_c_9998`), which an export file does
# not carry -- it carries the contract number -- so the two key spaces cannot be matched and a
# contract present in both would land twice. Keeping the export under its own source makes that
# overlap visible to any `group by source` instead of silently inflating `ebirja`, and the
# contract number stays recoverable from source_id for a future dedupe.
SOURCE = "ebirja_export"
MAPPING_PATH = Path(__file__).with_name("ebirja_export_mapping.yaml")

_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_WS = re.compile(r"\s+")
# A thousands separator may be a space, a non-breaking space or an apostrophe depending on who
# generated the file; the decimal separator may be a comma.
_NUM_STRIP = re.compile(r"[\s  '`]")


def normalize_header(value: Any) -> str:
    """Fold a header to the form synonyms are compared in: lowercase, no punctuation."""
    text = str(value or "").replace("’", "'").replace("ʻ", "'").strip().lower()
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


def load_column_mapping(path: Path | str = MAPPING_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class ColumnMatch:
    """Which column index each field was found at, and how."""

    columns: dict[str, int] = field(default_factory=dict)
    matched_on: dict[str, str] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)

    @property
    def missing_required(self) -> list[str]:
        return [f for f in self._required if f not in self.columns]

    _required: list[str] = field(default_factory=list)


def match_columns(headers: list[Any], mapping: dict[str, Any] | None = None) -> ColumnMatch:
    """Assign each mapped field to at most one column of this file.

    Every (field, synonym, column) triple is scored -- 3 for an exact fold match, 2 when the
    header contains the synonym, 1 when the synonym contains the header -- and the triples are
    then taken best-first, longest synonym breaking ties, with each field and each column used
    once. That ordering is what lets "buyurtmachi inn" take the STIR column before the shorter
    "buyurtmachi" can claim it as a customer name.
    """
    mapping = mapping or load_column_mapping()
    columns: dict[str, list[str]] = mapping.get("columns") or {}
    folded = [normalize_header(h) for h in headers]

    candidates: list[tuple[int, int, int, str, str]] = []
    for fname, synonyms in columns.items():
        for syn in synonyms or []:
            syn_f = normalize_header(syn)
            if not syn_f:
                continue
            for idx, head in enumerate(folded):
                if not head:
                    continue
                if head == syn_f:
                    score = 3
                elif syn_f in head:
                    score = 2
                elif head in syn_f:
                    score = 1
                else:
                    continue
                candidates.append((score, len(syn_f), -idx, fname, syn_f))

    candidates.sort(reverse=True)
    out = ColumnMatch(headers=[str(h) if h is not None else "" for h in headers])
    out._required = list(mapping.get("required") or [])
    used: set[int] = set()
    for _score, _length, neg_idx, fname, syn_f in candidates:
        idx = -neg_idx
        if fname in out.columns or idx in used:
            continue
        out.columns[fname] = idx
        out.matched_on[fname] = syn_f
        used.add(idx)
    out.unmatched = [f for f in columns if f not in out.columns]
    return out


def describe_columns(match: ColumnMatch) -> str:
    """Human-readable report of a real file's headers against the mapping."""
    lines = [f"file headers ({len(match.headers)}):"]
    for idx, head in enumerate(match.headers):
        owner = next((f for f, i in match.columns.items() if i == idx), None)
        lines.append(f"  [{idx:>2}] {head!r}" + (f"  -> {owner}" if owner else "  -- unused"))
    lines.append("matched fields:")
    for fname, idx in sorted(match.columns.items(), key=lambda kv: kv[1]):
        lines.append(f"  {fname:<16} column {idx} ({match.matched_on[fname]!r})")
    if match.unmatched:
        lines.append("unmatched fields (add the real wording to ebirja_export_mapping.yaml):")
        lines.append("  " + ", ".join(sorted(match.unmatched)))
    if match.missing_required:
        lines.append("MISSING REQUIRED: " + ", ".join(match.missing_required))
    return "\n".join(lines)


def read_table(path: Path | str) -> tuple[list[Any], list[list[Any]]]:
    """Read an .xlsx or .csv export into (headers, rows).

    The header is the first row that fills at least two cells: cabinet exports often open with
    a title line and a blank line before the real header.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        try:
            ws = wb.worksheets[0]
            raw = [list(r) for r in ws.iter_rows(values_only=True)]
        finally:
            wb.close()
    elif suffix in (".csv", ".tsv", ".txt"):
        delimiter = "\t" if suffix == ".tsv" else None
        with open(p, encoding="utf-8-sig", newline="") as fh:
            sample = fh.read(8192)
            fh.seek(0)
            if delimiter is None:
                try:
                    delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
                except csv.Error:
                    delimiter = ","
            raw = [list(r) for r in csv.reader(fh, delimiter=delimiter)]
    else:
        raise ValueError(f"unsupported export format {p.suffix!r} (expected .xlsx or .csv)")

    for i, row in enumerate(raw):
        if sum(1 for c in row if str(c or "").strip()) >= 2:
            return row, [r for r in raw[i + 1 :] if any(str(c or "").strip() for c in r)]
    return [], []


def _cell(row: list[Any], match: ColumnMatch, fname: str) -> str | None:
    idx = match.columns.get(fname)
    if idx is None or idx >= len(row):
        return None
    text = str(row[idx]).strip() if row[idx] is not None else ""
    return text or None


def parse_amount(value: Any) -> Decimal | None:
    """Parse a money or quantity cell, tolerating spaced thousands and a comma decimal."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    text = _NUM_STRIP.sub("", str(value)).strip()
    if not text:
        return None
    # Only treat a comma as the decimal point; a file using it as a thousands separator would
    # have had it stripped above only if spaced, so prefer the conservative reading.
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    text = text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


@dataclass
class ExportReport:
    """What a file turned into, including the two ambiguities worth seeing."""

    path: str = ""
    rows: int = 0
    skipped: int = 0
    contracts: int = 0
    items: int = 0
    multi_row_contracts: int = 0
    varying_amount_contracts: int = 0

    def summary(self) -> str:
        lines = [
            f"{self.path}: rows={self.rows} unusable={self.skipped} "
            f"contracts={self.contracts} items={self.items}",
        ]
        if self.multi_row_contracts:
            lines.append(
                f"  {self.multi_row_contracts} contract(s) span several rows, grouped into one "
                "procedure each"
            )
        if self.varying_amount_contracts:
            lines.append(
                f"  WARNING: {self.varying_amount_contracts} contract(s) carry a different "
                "amount on each of their rows, so the amount column is per line item, not the "
                "contract total. Point `amount` at the contract-total column in "
                "ebirja_export_mapping.yaml, or the stored price will be one line of it."
            )
        return "\n".join(lines)


def load_ebirja_export(
    path: Path | str, mapping: dict[str, Any] | None = None
) -> tuple[list[ProcedureRecord], ExportReport, ColumnMatch]:
    """Parse one export file into ProcedureRecords, one per contract number."""
    headers, rows = read_table(path)
    match = match_columns(headers, mapping)
    report = ExportReport(path=str(path), rows=len(rows))
    if match.missing_required:
        raise ValueError(
            "export file is missing required column(s): "
            + ", ".join(match.missing_required)
            + ".\n"
            + describe_columns(match)
        )

    grouped: dict[str, list[list[Any]]] = {}
    for row in rows:
        number = _cell(row, match, "contract_number")
        product = _cell(row, match, "product_name")
        if not number or not product:
            report.skipped += 1
            continue
        grouped.setdefault(number, []).append(row)

    records: list[ProcedureRecord] = []
    for number, group in grouped.items():
        if len(group) > 1:
            report.multi_row_contracts += 1
        amounts = {
            parse_amount(_cell(r, match, "amount"))
            for r in group
            if _cell(r, match, "amount") is not None
        }
        if len(amounts) > 1:
            report.varying_amount_contracts += 1
        # First non-empty amount, never the sum: if the column holds the contract total it is
        # repeated on every row, and summing it would multiply the contract by its line count.
        amount = next(
            (a for a in (parse_amount(_cell(r, match, "amount")) for r in group) if a), None
        )

        head = group[0]
        signed_at = parse_datetime(_cell(head, match, "contract_date"))
        supplier_name = _cell(head, match, "supplier_name")
        supplier_stir = _cell(head, match, "supplier_stir")
        currency = (_cell(head, match, "currency") or "UZS").upper()[:8]

        items = [
            LotItemRecord(
                raw_name=str(_cell(r, match, "product_name"))[:1000],
                quantity=parse_amount(_cell(r, match, "quantity")),
                unit=(_cell(r, match, "unit") or None),
                unit_price_raw=(_cell(r, match, "unit_price") or None),
            )
            for r in group
        ]
        report.items += len(items)

        award = None
        if supplier_name or supplier_stir or amount is not None:
            award = AwardRecord(
                supplier_name=supplier_name,
                supplier_stir=supplier_stir,
                amount=amount,
                awarded_at=signed_at,
            )

        lot_number = _cell(head, match, "lot_number")
        title = str(items[0].raw_name)
        records.append(
            ProcedureRecord(
                source_id=f"ebirja_x_{number}"[:64],
                source_url=None,
                procedure_type=_cell(head, match, "procedure_type") or "E-Birja shartnoma",
                title=(f"{title} (lot {lot_number})" if lot_number else title)[:500],
                status="COMPLETED",
                published_at=signed_at,
                deadline_at=None,
                completed_at=signed_at,
                currency=currency,
                start_price=amount,
                customer_name=_cell(head, match, "customer_name"),
                customer_stir=_cell(head, match, "customer_stir"),
                customer_region=_cell(head, match, "region"),
                items=items,
                award=award,
            )
        )

    report.contracts = len(records)
    return records, report, match


def import_ebirja_export(session: Session, records: list[ProcedureRecord]) -> dict[str, int]:
    """Idempotent upsert keyed on (source='ebirja_export', source_id)."""
    return import_ebirja_records(session, records, source=SOURCE)
