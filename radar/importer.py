"""Resumable, idempotent importer.

Per list page (one transaction): store list snapshot -> for each entry fetch and
store the detail snapshot -> upsert organization/procedure/lot_item/award ->
advance import_cursor. A crash inside a page rolls the whole page back, so the
cursor always points at the last fully-committed page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from radar.models import (
    Award,
    ImportCursor,
    LotItem,
    Organization,
    OrganizationAlias,
    Procedure,
)
from radar.snapshots import store_snapshot
from radar.source.client import Source, SourceError
from radar.source.parser import ProcedureRecord, parse_detail, parse_list_page

log = logging.getLogger(__name__)
JOB_NAME = "uzex_completed"


@dataclass
class ImportStats:
    pages: int = 0
    listed: int = 0
    fetched_details: int = 0
    inserted: int = 0
    updated: int = 0
    skipped_existing: int = 0
    stopped_reason: str | None = None
    errors: list[str] = field(default_factory=list)


def canonical_name(name: str) -> str:
    return " ".join(name.split()).strip()


def upsert_organization(session: Session, name: str | None, stir: str | None,
                        region: str | None = None) -> Organization | None:
    if not name and not stir:
        return None
    name = canonical_name(name or stir or "")
    org: Organization | None = None
    if stir:
        org = session.scalar(select(Organization).where(Organization.stir == stir))
    if org is None:
        alias = session.scalar(
            select(OrganizationAlias)
            .join(Organization)
            .where(OrganizationAlias.name_raw == name,
                   (Organization.stir == stir) | (Organization.stir.is_(None)))
        )
        org = alias.organization if alias else None
    if org is None:
        org = Organization(stir=stir, name_canonical=name, region=region)
        session.add(org)
        session.flush()
    else:
        if stir and not org.stir:
            org.stir = stir
        if region and not org.region:
            org.region = region
    if name and not any(a.name_raw == name for a in org.aliases):
        session.add(OrganizationAlias(org_id=org.id, name_raw=name))
        session.flush()
    return org


def upsert_procedure(session: Session, rec: ProcedureRecord, snapshot_id: int | None,
                     source: str = "uzex") -> tuple[Procedure, bool]:
    customer = upsert_organization(session, rec.customer_name, rec.customer_stir,
                                   rec.customer_region)
    values = dict(
        source=source, source_id=rec.source_id, source_url=rec.source_url,
        procedure_type=rec.procedure_type,
        customer_org_id=customer.id if customer else None,
        title=rec.title, published_at=rec.published_at, deadline_at=rec.deadline_at,
        completed_at=rec.completed_at, status=rec.status, currency=rec.currency,
        start_price=rec.start_price, raw_snapshot_id=snapshot_id,
    )
    stmt = pg_insert(Procedure).values(**values)
    update_cols = {k: stmt.excluded[k] for k in values if k not in ("source", "source_id")}
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(constraint="uq_procedure_source_id", set_=update_cols)
    stmt = stmt.returning(Procedure.id, Procedure.created_at == Procedure.updated_at)
    row = session.execute(stmt).one()
    proc_id, created = row[0], bool(row[1])
    proc = session.get(Procedure, proc_id)
    assert proc is not None
    # lot items: replace-all keeps re-parsing from snapshots deterministic
    for item in list(proc.items):
        session.delete(item)
    session.flush()
    for item in rec.items:
        session.add(LotItem(procedure_id=proc.id, raw_name=item.raw_name, quantity=item.quantity,
                            unit=item.unit, unit_price_raw=item.unit_price_raw))
    if rec.award:
        supplier = upsert_organization(session, rec.award.supplier_name, rec.award.supplier_stir)
        award = session.get(Award, proc.id)
        if award is None:
            award = Award(procedure_id=proc.id)
            session.add(award)
        award.supplier_org_id = supplier.id if supplier else None
        award.amount = rec.award.amount
        award.awarded_at = rec.award.awarded_at
    session.flush()
    return proc, created


def get_cursor(session: Session, job_name: str = JOB_NAME) -> ImportCursor:
    cur = session.get(ImportCursor, job_name)
    if cur is None:
        cur = ImportCursor(job_name=job_name, last_page=0, last_source_id=None)
        session.add(cur)
        session.flush()
    return cur


def run_import(session: Session, source: Source, *, since: datetime | None = None,
               limit: int | None = None, refresh: bool = False,
               job_name: str = JOB_NAME, max_pages: int = 100_000,
               first_page: int = 1) -> ImportStats:
    """Import completed procedures. Commits after every page; resumes from the cursor."""
    stats = ImportStats()
    cursor = get_cursor(session, job_name)
    session.commit()  # the cursor row must survive a rolled-back page
    page = max(cursor.last_page + 1, first_page)
    processed = 0
    while page < first_page + max_pages:
        if limit is not None and processed >= limit:
            stats.stopped_reason = "limit"
            break
        try:
            fetched = source.list_page(page)
        except SourceError as exc:
            stats.stopped_reason = f"{type(exc).__name__}: {exc}"
            log.error("stopping import: %s", exc)
            break
        listing = parse_list_page(fetched.body)
        if not listing.entries:
            stats.stopped_reason = "end_of_listing"
            break
        stats.pages += 1
        store_snapshot(session, fetched.url, fetched.body)
        older_than_since = False
        last_source_id = None
        for entry in listing.entries:
            if limit is not None and processed >= limit:
                break
            stats.listed += 1
            if since and entry.completed_at and entry.completed_at < since:
                older_than_since = True
                continue
            existing = session.scalar(
                select(Procedure.id).where(Procedure.source == source.name,
                                           Procedure.source_id == entry.source_id)
            )
            if existing and not refresh:
                stats.skipped_existing += 1
                processed += 1
                last_source_id = entry.source_id
                continue
            try:
                detail = source.detail(entry.source_id)
            except SourceError as exc:
                stats.stopped_reason = f"{type(exc).__name__}: {exc}"
                log.error("stopping import mid-page %s: %s", page, exc)
                session.rollback()
                return stats
            stats.fetched_details += 1
            snap = store_snapshot(session, detail.url, detail.body)
            try:
                rec = parse_detail(detail.body)
            except (ValueError, KeyError) as exc:
                stats.errors.append(f"{entry.source_id}: {exc}")
                log.warning("unparseable detail %s: %s", entry.source_id, exc)
                continue
            _, created = upsert_procedure(session, rec, snap.id, source=source.name)
            if created:
                stats.inserted += 1
            else:
                stats.updated += 1
            processed += 1
            last_source_id = entry.source_id
        cursor.last_page = page
        cursor.last_source_id = last_source_id or cursor.last_source_id
        session.commit()
        log.info("page %d committed (%d listed, %d inserted, %d updated)", page, stats.listed,
                 stats.inserted, stats.updated)
        if older_than_since:
            stats.stopped_reason = "since"
            break
        page += 1
    else:
        stats.stopped_reason = "max_pages"
    session.commit()
    return stats


def reset_cursor(session: Session, job_name: str = JOB_NAME) -> None:
    cur = session.get(ImportCursor, job_name)
    if cur:
        cur.last_page = 0
        cur.last_source_id = None
        session.flush()
