"""Excel export: out/renewal_radar.xlsx with Radar, IT_Lots and Stats sheets."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.models import Award, Classification, Organization, Procedure
from radar.renewal import radar_rows
from radar.stats import collect_stats

log = logging.getLogger(__name__)

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True)
WARN_FONT = Font(color="9C0006", bold=True)

RADAR_HEADERS = ["Customer", "STIR", "Region", "Category", "Brand", "Last purchase", "Amount",
                 "Expected renewal", "Contact by", "Score", "Source URL", "Lot title"]
IT_HEADERS = ["Source", "Source ID", "Completed", "Customer", "STIR", "Region", "Category",
              "Brand", "Method", "Model", "Confidence", "Amount", "Currency", "Title",
              "Source URL"]


def _date(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def _style_header(sheet, headers: list[str]) -> None:
    sheet.append(headers)
    for cell in sheet[sheet.max_row]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    # Coordinate string, not sheet.cell(): touching a cell would materialise an
    # empty row and push the first data row down by one.
    sheet.freeze_panes = f"A{sheet.max_row + 1}"


def _autosize(sheet, widths: dict[int, int]) -> None:
    for index, width in widths.items():
        sheet.column_dimensions[get_column_letter(index)].width = width


def _sources(session: Session) -> list[str]:
    return sorted(s for s in session.scalars(select(Procedure.source).distinct()) if s)


def export_workbook(session: Session, path: str | Path, now: datetime | None = None,
                    limit: int | None = None) -> tuple[Path, int]:
    now = now or datetime.now(UTC)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sources = _sources(session)
    synthetic = [s for s in sources if s != "uzex"]

    book = Workbook()
    radar = book.active
    radar.title = "Radar"
    if synthetic:
        radar.append([f"WARNING: contains data from non-production sources {synthetic}. "
                      "These rows are synthetic fixtures, not real procurement results."])
        radar["A1"].font = WARN_FONT
        radar.append([])
    _style_header(radar, RADAR_HEADERS)

    rows = radar_rows(session, now=now, limit=limit)
    for row in rows:
        radar.append([row.customer, row.stir or "", row.region or "", row.category or "",
                      row.brand or "", _date(row.last_purchase_at),
                      float(row.amount) if row.amount is not None else None,
                      _date(row.expected_renewal_at), _date(row.contact_by_at), row.score,
                      row.source_url or "", row.title])
    _autosize(radar, {1: 46, 2: 12, 3: 20, 4: 18, 5: 14, 6: 14, 7: 18, 8: 16, 9: 14, 10: 8,
                      11: 40, 12: 50})

    lots = book.create_sheet("IT_Lots")
    _style_header(lots, IT_HEADERS)
    amount = func.coalesce(Award.amount, Procedure.start_price)
    stmt = (select(Procedure, Classification, Organization, amount)
            .join(Classification, Classification.procedure_id == Procedure.id)
            .join(Organization, Organization.id == Procedure.customer_org_id, isouter=True)
            .join(Award, Award.procedure_id == Procedure.id, isouter=True)
            .where(Classification.is_it.is_(True))
            .order_by(Procedure.completed_at.desc().nullslast()))
    it_count = 0
    for proc, cls, org, value in session.execute(stmt).all():
        lots.append([proc.source, proc.source_id, _date(proc.completed_at),
                     org.name_canonical if org else "", org.stir if org else "",
                     org.region if org else "", cls.category or "", cls.brand or "",
                     cls.method, cls.model_name or "",
                     float(cls.confidence) if cls.confidence is not None else None,
                     float(value) if value is not None else None, proc.currency or "",
                     proc.title, proc.source_url or ""])
        it_count += 1
    _autosize(lots, {1: 12, 2: 14, 3: 12, 4: 46, 5: 12, 6: 20, 7: 18, 8: 14, 9: 8, 10: 16,
                     11: 10, 12: 18, 13: 9, 14: 60, 15: 40})

    stats = book.create_sheet("Stats")
    _style_header(stats, ["Metric", "Value"])
    stats.append(["generated_at", now.strftime("%Y-%m-%d %H:%M UTC")])
    stats.append(["radar_rows", len(rows)])
    stats.append(["it_lots", it_count])
    for key, value in collect_stats(session).items():
        stats.append([key, str(value) if isinstance(value, dict) else value])
    stats.append(["data_note", "Rows from sources other than 'uzex' are synthetic fixtures."])
    _autosize(stats, {1: 30, 2: 70})

    book.save(path)
    log.info("wrote %s (%d radar rows, %d IT lots)", path, len(rows), it_count)
    return path, len(rows)
