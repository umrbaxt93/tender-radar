"""Comprehensive historical migration from SQLite to PostgreSQL.

Migrates all 1,058 lots, 1,076 contract items, and 412 companies
from SQLite (UZEX, XT-Xarid, E-Birja, Cooperation) into the PostgreSQL
Tender Radar database with complete idempotency and normalization.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.classify.rules import build_text, classify_text
from radar.models import Award, Classification, LotItem, Organization, OrganizationAlias, Procedure
from radar.normalize import normalize_product

log = logging.getLogger(__name__)

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[2] / "data" / "softy_procurement.db"


def parse_dt(s: str | None) -> datetime | None:
    """Parse ISO or date strings into timezone-aware UTC datetime."""
    if not s:
        return None
    try:
        clean = s.strip().replace("Z", "+00:00")
        if len(clean) == 10 and clean[4] == "-" and clean[7] == "-":
            clean = f"{clean}T00:00:00+00:00"
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        return None


def _get_or_create_org(
    session: Session,
    stir: str | None,
    name: str | None,
    region: str | None = None,
) -> Organization | None:
    """Find or create an organization by STIR or canonical name with aliases."""
    clean_stir = stir.strip() if stir and stir.strip() else None
    clean_name = (name or "").strip()

    if not clean_stir and not clean_name:
        return None

    org: Organization | None = None

    if clean_stir:
        org = session.scalar(select(Organization).where(Organization.stir == clean_stir))

    if not org and clean_name:
        alias = session.scalar(
            select(OrganizationAlias).where(OrganizationAlias.name_raw == clean_name)
        )
        if alias:
            org = session.get(Organization, alias.org_id)

    if not org:
        canonical = clean_name if clean_name else f"STIR {clean_stir}"
        org = Organization(
            stir=clean_stir,
            name_canonical=canonical,
            region=region,
        )
        session.add(org)
        session.flush()

    if clean_name:
        existing_alias = session.scalar(
            select(OrganizationAlias).where(
                OrganizationAlias.org_id == org.id,
                OrganizationAlias.name_raw == clean_name,
            )
        )
        if not existing_alias:
            session.add(OrganizationAlias(org_id=org.id, name_raw=clean_name))
            session.flush()

    return org


def migrate_all_sqlite(
    session: Session,
    sqlite_path: Path | str | None = None,
) -> dict[str, Any]:
    """Migrate all historical procurement records from SQLite into PostgreSQL."""
    db_path = Path(sqlite_path or DEFAULT_SQLITE_PATH)
    if not db_path.is_file():
        raise FileNotFoundError(f"SQLite procurement database not found at: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    stats = {
        "companies_synced": 0,
        "lots_considered": 0,
        "procedures_inserted": 0,
        "procedures_updated": 0,
        "items_migrated": 0,
        "awards_migrated": 0,
        "classifications_migrated": 0,
    }

    # 1. Sync companies
    cur.execute("SELECT * FROM companies;")
    company_rows = cur.fetchall()
    for crow in company_rows:
        inn = crow["inn"]
        cname = crow["name"]
        cregion = crow["region"]
        org = _get_or_create_org(session, inn, cname, cregion)
        if org:
            stats["companies_synced"] += 1
    session.flush()

    # 2. Sync all lots
    cur.execute("SELECT * FROM lots ORDER BY id ASC;")
    lots = cur.fetchall()
    stats["lots_considered"] = len(lots)

    for lot in lots:
        platform = (lot["platform_id"] or "").strip().lower()
        lot_raw_id = str(lot["id"] or "")
        lot_num = str(lot["lot_number"] or "").strip()

        if not platform:
            if lot_raw_id.startswith("uzex_"):
                platform = "uzex"
            elif lot_raw_id.startswith("xt_"):
                platform = "xt_xarid"
            elif lot_raw_id.startswith("ebirja_"):
                platform = "ebirja"
            else:
                platform = "uzex"

        source_id = lot_num or lot_raw_id.replace(f"{platform}_", "")
        title = lot["title"] or f"Lot {source_id}"

        # Buyer Organization
        cust_org = _get_or_create_org(
            session,
            lot["buyer_inn"],
            lot["buyer_name"],
            lot["region"],
        )

        dt_completed = parse_dt(lot["contract_date"]) or parse_dt(lot["result_date"])
        dt_published = parse_dt(lot["announcement_date"])
        dt_deadline = parse_dt(lot["deadline_date"])

        price: Decimal | None = None
        if lot["final_price"] is not None:
            price = Decimal(str(lot["final_price"]))
        elif lot["start_price"] is not None:
            price = Decimal(str(lot["start_price"]))

        source_url = lot["source_url"] or ""
        if not source_url:
            if platform == "uzex":
                source_url = f"https://xarid.uzex.uz/purchase/detail/{source_id}"
            elif platform == "xt_xarid":
                source_url = f"https://xt-xarid.uz/contract/{source_id}.1.1"
            elif platform == "ebirja":
                source_url = f"https://xarid.ebirja.uz/contract/{source_id}"
            else:
                source_url = f"https://xarid.uzex.uz/purchase/detail/{source_id}"

        proc = session.scalar(
            select(Procedure).where(
                Procedure.source == platform,
                Procedure.source_id == source_id,
            )
        )

        if not proc:
            proc = Procedure(
                source=platform,
                source_id=source_id,
                source_url=source_url,
                procedure_type=lot["procurement_type"] or "Davlat xaridi",
                customer_org_id=cust_org.id if cust_org else None,
                title=title,
                published_at=dt_published,
                deadline_at=dt_deadline,
                completed_at=dt_completed,
                status=lot["official_status"] or "COMPLETED",
                currency=lot["currency"] or "UZS",
                start_price=price,
            )
            session.add(proc)
            session.flush()
            stats["procedures_inserted"] += 1
        else:
            proc.title = title
            if cust_org:
                proc.customer_org_id = cust_org.id
            if dt_completed:
                proc.completed_at = dt_completed
            if price is not None:
                proc.start_price = price
            session.flush()
            stats["procedures_updated"] += 1

        # 3. Contract Items
        cur.execute("SELECT * FROM contract_items WHERE lot_id = ?;", (lot["id"],))
        item_rows = cur.fetchall()

        # Delete previous lot items for clean idempotent replacement
        existing_items = list(
            session.scalars(select(LotItem).where(LotItem.procedure_id == proc.id))
        )
        for itm in existing_items:
            session.delete(itm)
        session.flush()

        raw_item_names: list[str] = []
        if item_rows:
            for it in item_rows:
                raw_name = it["product_name"] or title
                raw_item_names.append(raw_name)
                norm = normalize_product(raw_name)
                li = LotItem(
                    procedure_id=proc.id,
                    raw_name=raw_name,
                    brand=norm.brand or it["brand"],
                    product_family=norm.product_family or it["product_family"],
                    model=norm.model,
                    term_months=norm.term_months,
                    quantity=Decimal(str(it["quantity"])) if it["quantity"] else Decimal(1),
                    unit=it["unit"] or "dona",
                    unit_price_raw=str(it["unit_price"]) if it["unit_price"] else None,
                )
                session.add(li)
                stats["items_migrated"] += 1
        else:
            norm = normalize_product(title)
            li = LotItem(
                procedure_id=proc.id,
                raw_name=title,
                brand=norm.brand,
                product_family=norm.product_family,
                model=norm.model,
                term_months=norm.term_months,
                quantity=Decimal(1),
                unit="dona",
                unit_price_raw=str(price) if price else None,
            )
            session.add(li)
            raw_item_names.append(title)
            stats["items_migrated"] += 1
        session.flush()

        # 4. Award (Winner / Supplier)
        supp_name = lot["supplier_name"] or lot["winner_name"]
        supp_inn = lot["supplier_inn"]
        if supp_name or price is not None:
            supp_org = _get_or_create_org(session, supp_inn, supp_name)
            award = session.scalar(
                select(Award).where(Award.procedure_id == proc.id)
            )
            if not award:
                award = Award(
                    procedure_id=proc.id,
                    supplier_org_id=supp_org.id if supp_org else None,
                    amount=price,
                    awarded_at=dt_completed,
                )
                session.add(award)
            else:
                if supp_org:
                    award.supplier_org_id = supp_org.id
                if price is not None:
                    award.amount = price
                if dt_completed:
                    award.awarded_at = dt_completed
            session.flush()
            stats["awards_migrated"] += 1

        # 5. Classification
        clf = session.scalar(
            select(Classification).where(Classification.procedure_id == proc.id)
        )
        text_corpus = build_text(title, raw_item_names)
        rule = classify_text(text_corpus)
        is_it = rule.likely_it == "yes"

        if not clf:
            clf = Classification(
                procedure_id=proc.id,
                is_it=is_it,
                category=rule.category,
                subcategory=None,
                brand=rule.brand,
                is_subscription=rule.is_subscription,
                term_months=rule.term_months,
                method="rule",
                confidence=0.9 if is_it else 0.5,
            )
            session.add(clf)
        else:
            clf.is_it = is_it
            clf.category = rule.category
            clf.brand = rule.brand
            clf.is_subscription = rule.is_subscription
            clf.term_months = rule.term_months
            clf.method = "rule"
        session.flush()
        stats["classifications_migrated"] += 1

    conn.close()
    return stats
