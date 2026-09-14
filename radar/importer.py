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
    RawSnapshot,
)
from radar.snapshots import snapshot_body, store_snapshot
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


def find_similar_organization(session: Session, name: str,
                              threshold: float) -> Organization | None:
    """Best trigram match among organizations that carry no STIR.

    Only STIR-less organizations are candidates. An organization with a STIR is already
    identified, and merging two identified organizations because their names look alike
    would corrupt the customer history that the whole Radar is built on.
    """
    similarity = func.similarity(func.lower(OrganizationAlias.name_raw), name.lower())
    row = session.execute(
        select(Organization, similarity.label("score"))
        .join(OrganizationAlias, OrganizationAlias.org_id == Organization.id)
        .where(Organization.stir.is_(None), similarity >= threshold)
        .order_by(similarity.desc())
        .limit(1)
    ).first()
    return row[0] if row else None


def upsert_organization(session: Session, name: str | None, stir: str | None,
                        region: str | None = None,
                        match_threshold: float | None = None) -> Organization | None:
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
            .where((OrganizationAlias.name_raw == name) |
                   (func.lower(OrganizationAlias.name_raw) == name.lower()),
                   (Organization.stir == stir) | (Organization.stir.is_(None)))
        )
        org = alias.organization if alias else None
    if org is None and match_threshold:
        # Same customer written slightly differently, with no STIR to tie them together.
        org = find_similar_organization(session, name, match_threshold)
    if org is None:
        org = Organization(stir=stir, name_canonical=name, region=region)
        session.add(org)
        session.flush()
    else:
        if stir and not org.stir:
            org.stir = stir
        if region and not org.region:
            org.region = region
    if name:
        # Check existing aliases in Python to support all Unicode/Cyrillic
        # encodings regardless of DB collation.
        existing_aliases = session.scalars(
            select(OrganizationAlias.name_raw).where(OrganizationAlias.org_id == org.id)
        ).all()
        if not any(a.strip().lower() == name.lower() for a in existing_aliases):
            session.execute(
                pg_insert(OrganizationAlias)
                .values(org_id=org.id, name_raw=name)
                .on_conflict_do_nothing(constraint="uq_org_alias")
            )
            session.flush()
    return org


def upsert_procedure(session: Session, rec: ProcedureRecord, snapshot_id: int | None,
                     source: str = "uzex",
                     match_threshold: float | None = None) -> tuple[Procedure, bool]:
    customer = upsert_organization(session, rec.customer_name, rec.customer_stir,
                                   rec.customer_region, match_threshold)
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
        supplier = upsert_organization(session, rec.award.supplier_name,
                                       rec.award.supplier_stir, None, match_threshold)
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
               first_page: int = 1, match_threshold: float | None = None) -> ImportStats:
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
            _, created = upsert_procedure(session, rec, snap.id, source=source.name,
                                          match_threshold=match_threshold)
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


@dataclass
class ReparseStats:
    """Result of rebuilding rows from stored snapshots without touching the network."""
    considered: int = 0
    reparsed: int = 0
    checksum_failures: int = 0
    parse_failures: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"reparse: considered={self.considered} reparsed={self.reparsed} "
                f"checksum_failures={self.checksum_failures} "
                f"parse_failures={self.parse_failures}")


def reparse_from_snapshots(session: Session, limit: int | None = None,
                           match_threshold: float | None = None,
                           dry_run: bool = False) -> ReparseStats:
    """Re-run parsing over stored raw snapshots.

    docs/SPEC.md requires that parsing be re-runnable from snapshots, so a mapping or
    parser fix never means re-fetching from the source. Checksums are verified on the way
    in; a corrupted snapshot is reported and skipped rather than silently reparsed.
    """
    stats = ReparseStats()
    stmt = (select(Procedure.id, Procedure.source, RawSnapshot)
            .join(RawSnapshot, RawSnapshot.id == Procedure.raw_snapshot_id)
            .order_by(Procedure.id))
    if limit:
        stmt = stmt.limit(limit)
    for _pid, source, snap in session.execute(stmt).all():
        stats.considered += 1
        try:
            body = snapshot_body(snap)
        except ValueError as exc:
            stats.checksum_failures += 1
            stats.errors.append(f"snapshot {snap.id}: {exc}")
            log.error("snapshot %s failed its checksum; skipping", snap.id)
            continue
        try:
            rec = parse_detail(body)
        except (ValueError, KeyError) as exc:
            stats.parse_failures += 1
            stats.errors.append(f"snapshot {snap.id}: {exc}")
            continue
        if not dry_run:
            upsert_procedure(session, rec, snap.id, source=source,
                             match_threshold=match_threshold)
        stats.reparsed += 1
    if dry_run:
        session.rollback()
    else:
        session.commit()
    log.info("%s", stats.summary())
    return stats
