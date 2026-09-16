"""Excel export: out/renewal_radar.xlsx with Radar, IT_Lots and Stats sheets."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.models import (
    Award,
    Classification,
    LotItem,
    Organization,
    Procedure,
    RenewalOpportunity,
)
from radar.privacy import mask_identifier
from radar.renewal import radar_rows
from radar.security import sanitize_for_spreadsheet
from radar.stats import collect_stats

log = logging.getLogger(__name__)

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True)
WARN_FONT = Font(color="9C0006", bold=True)

RADAR_HEADERS = [
    "Customer",
    "STIR",
    "Region",
    "Category",
    "Brand",
    "Last purchase",
    "Amount",
    "Expected renewal",
    "Contact by",
    "Score",
    "Source URL",
    "Lot title",
]
EXPORT_10COL_HEADERS = [
    "Korxona nomi",
    "Tashkilot INN/JSHSHIR",
    "Mahsulot nomi",
    "Shartnoma tuzilgan sana",
    "Shartnoma tugash sanasi",
    "Boshlang'ich summa (so'm)",
    "Yutilgan summa (so'm)",
    "Yutib olgan korxona nomi",
    "Yutib olgan korxona INN/JSHSHIR",
    "Lot silkasi",
]
IT_HEADERS = [
    "Source",
    "Source ID",
    "Completed",
    "Customer",
    "STIR",
    "Region",
    "Category",
    "Brand",
    "Method",
    "Model",
    "Confidence",
    "Amount",
    "Currency",
    "Title",
    "Source URL",
]


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


def _export_10columns_sheet(
    sheet, session: Session, limit: int | None = None, is_admin: bool = False
) -> int:
    """The buyer-facing sheet: customer, product, dates, both sums, winner and lot link."""
    _style_header(sheet, EXPORT_10COL_HEADERS)
    amount_col = func.coalesce(Award.amount, Procedure.start_price)
    stmt = (
        select(Procedure, Organization, Award, LotItem, RenewalOpportunity, amount_col)
        .join(Classification, Classification.procedure_id == Procedure.id)
        .join(Organization, Organization.id == Procedure.customer_org_id, isouter=True)
        .join(Award, Award.procedure_id == Procedure.id, isouter=True)
        .outerjoin(LotItem, LotItem.procedure_id == Procedure.id)
        .join(RenewalOpportunity, RenewalOpportunity.procedure_id == Procedure.id, isouter=True)
        .where(Classification.is_it.is_(True), Procedure.completed_at.is_not(None))
        .order_by(Procedure.completed_at.desc())
    )
    # No cap. Excel holds a million rows; truncating here would hide awarded contracts
    # from the one export that can actually carry all of them.
    if limit:
        stmt = stmt.limit(limit)

    row_count = 0
    for proc, cust_org, award, item, renewal, amount in session.execute(stmt).all():
        winner_org = award.supplier if award else None
        product_name = item.raw_name if item else (proc.title or "")
        signed_date = proc.completed_at.strftime("%Y-%m-%d") if proc.completed_at else ""
        # Hardware has no renewal row, so fall back to the lot deadline and finally to a
        # one-year term, matching the dashboard export. An empty cell here reads as
        # "no contract end", which is wrong for a one-off purchase.
        end_at = (
            renewal.expected_renewal_at
            if renewal and renewal.expected_renewal_at
            else proc.deadline_at
            or (proc.completed_at + timedelta(days=365) if proc.completed_at else None)
        )
        end_date = end_at.strftime("%Y-%m-%d") if end_at else ""

        sheet.append(
            [
                sanitize_for_spreadsheet(cust_org.name_canonical if cust_org else ""),
                sanitize_for_spreadsheet(
                    mask_identifier(cust_org.stir, is_admin=is_admin) if cust_org else ""
                ),
                sanitize_for_spreadsheet(product_name),
                signed_date,
                end_date,
                float(proc.start_price) if proc.start_price is not None else None,
                float(amount) if amount is not None else None,
                sanitize_for_spreadsheet(winner_org.name_canonical if winner_org else ""),
                sanitize_for_spreadsheet(
                    mask_identifier(winner_org.stir, is_admin=is_admin) if winner_org else ""
                ),
                sanitize_for_spreadsheet(proc.source_url or ""),
            ]
        )
        row_count += 1

    _autosize(sheet, {1: 46, 2: 12, 3: 40, 4: 16, 5: 16, 6: 14, 7: 14, 8: 46, 9: 12, 10: 40})
    return row_count


def export_workbook(
    session: Session,
    path: str | Path,
    now: datetime | None = None,
    limit: int | None = None,
    is_admin: bool = False,
) -> tuple[Path, int]:
    now = now or datetime.now(UTC)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sources = _sources(session)
    synthetic = [s for s in sources if s != "uzex"]

    book = Workbook()
    radar = book.active
    radar.title = "Radar"
    if synthetic:
        radar.append(
            [
                f"WARNING: contains data from non-production sources {synthetic}. "
                "These rows are synthetic fixtures, not real procurement results."
            ]
        )
        radar["A1"].font = WARN_FONT
        radar.append([])
    _style_header(radar, RADAR_HEADERS)

    rows = radar_rows(session, now=now, limit=limit)
    for row in rows:
        radar.append(
            [
                sanitize_for_spreadsheet(row.customer),
                sanitize_for_spreadsheet(
                    mask_identifier(row.stir, is_admin=is_admin) if row.stir else ""
                ),
                sanitize_for_spreadsheet(row.region or ""),
                sanitize_for_spreadsheet(row.category or ""),
                sanitize_for_spreadsheet(row.brand or ""),
                _date(row.last_purchase_at),
                float(row.amount) if row.amount is not None else None,
                _date(row.expected_renewal_at),
                _date(row.contact_by_at),
                row.score,
                sanitize_for_spreadsheet(row.source_url or ""),
                sanitize_for_spreadsheet(row.title),
            ]
        )
    _autosize(
        radar,
        {1: 46, 2: 12, 3: 20, 4: 18, 5: 14, 6: 14, 7: 18, 8: 16, 9: 14, 10: 8, 11: 40, 12: 50},
    )

    lots = book.create_sheet("IT_Lots")
    _style_header(lots, IT_HEADERS)
    amount = func.coalesce(Award.amount, Procedure.start_price)
    stmt = (
        select(Procedure, Classification, Organization, amount)
        .join(Classification, Classification.procedure_id == Procedure.id)
        .join(Organization, Organization.id == Procedure.customer_org_id, isouter=True)
        .join(Award, Award.procedure_id == Procedure.id, isouter=True)
        .where(Classification.is_it.is_(True))
        .order_by(Procedure.completed_at.desc().nullslast())
    )
    it_count = 0
    for proc, cls, org, value in session.execute(stmt).all():
        lots.append(
            [
                sanitize_for_spreadsheet(proc.source),
                sanitize_for_spreadsheet(proc.source_id),
                _date(proc.completed_at),
                sanitize_for_spreadsheet(org.name_canonical if org else ""),
                sanitize_for_spreadsheet(
                    mask_identifier(org.stir, is_admin=is_admin) if org else ""
                ),
                sanitize_for_spreadsheet(org.region if org else ""),
                sanitize_for_spreadsheet(cls.category or ""),
                sanitize_for_spreadsheet(cls.brand or ""),
                sanitize_for_spreadsheet(cls.method),
                sanitize_for_spreadsheet(cls.model_name or ""),
                float(cls.confidence) if cls.confidence is not None else None,
                float(value) if value is not None else None,
                sanitize_for_spreadsheet(proc.currency or ""),
                sanitize_for_spreadsheet(proc.title),
                sanitize_for_spreadsheet(proc.source_url or ""),
            ]
        )
        it_count += 1
    _autosize(
        lots,
        {
            1: 12,
            2: 14,
            3: 12,
            4: 46,
            5: 12,
            6: 20,
            7: 18,
            8: 14,
            9: 8,
            10: 16,
            11: 10,
            12: 18,
            13: 9,
            14: 60,
            15: 40,
        },
    )

    export_10col = book.create_sheet("Export_10col")
    export_10col_count = _export_10columns_sheet(
        export_10col, session, limit=limit, is_admin=is_admin
    )

    stats = book.create_sheet("Stats")
    _style_header(stats, ["Metric", "Value"])
    stats.append(["generated_at", now.strftime("%Y-%m-%d %H:%M UTC")])
    stats.append(["radar_rows", len(rows)])
    stats.append(["it_lots", it_count])
    stats.append(["export_10col_rows", export_10col_count])
    for key, value in collect_stats(session).items():
        stats.append([key, str(value) if isinstance(value, dict) else value])
    stats.append(["data_note", "Rows from sources other than 'uzex' are synthetic fixtures."])
    _autosize(stats, {1: 30, 2: 70})

    book.save(path)
    log.info(
        "wrote %s (%d radar rows, %d IT lots, %d export rows)",
        path,
        len(rows),
        it_count,
        export_10col_count,
    )
    return path, len(rows)
