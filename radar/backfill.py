"""Historical backfill of the UZEX e-tender archive.

The live sync only ever sees the newest deals, so anything that happened before the
worker was first run is invisible. This walks the archive backwards in index order.

Two properties matter more than speed. Every batch is committed before the cursor
advances, so an interrupted run resumes where it stopped rather than refetching from
the start. And the list rows are used as they arrive, without a per-deal detail call:
the list already carries customer and provider STIR, both sums and the contract date,
which is the whole ten-column export. Fetching the detail for every deal would add one
paced request each -- at the mandatory 3 s floor that is months of wall clock for the
95% of rows that are not IT at all.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.importer import get_cursor
from radar.models import Procedure
from radar.source.uzex import UzexClient, import_uzex_records, parse_uzex_etender_deal

log = logging.getLogger(__name__)

JOB_NAME = "uzex_etender_backfill"
BATCH_SIZE = 500
# The archive reports ~161k e-tender deals. This only stops a bug from looping forever.
MAX_BATCHES = 2000


@dataclass
class BackfillStats:
    batches: int = 0
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    oldest_seen: datetime | None = None
    stopped_because: str = "not started"
    cursor_mismatch: str | None = None
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        oldest = self.oldest_seen.strftime("%Y-%m-%d") if self.oldest_seen else "-"
        warning = f" WARNING: {self.cursor_mismatch}" if self.cursor_mismatch else ""
        return (f"backfill: {self.batches} batches, {self.fetched} deals fetched, "
                f"{self.inserted} new, {self.updated} updated, {self.skipped} unparsable, "
                f"oldest {oldest}, stopped: {self.stopped_because}{warning}")


def _deal_date(deal: dict) -> datetime | None:
    raw = deal.get("deal_date") or deal.get("deal_contract_date")
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(raw)[:19], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def backfill_etender(
    session: Session,
    client: UzexClient | None = None,
    *,
    years: float = 3.0,
    batch_size: int = BATCH_SIZE,
    now: datetime | None = None,
    job_name: str = JOB_NAME,
    max_batches: int = MAX_BATCHES,
    restart: bool = False,
) -> BackfillStats:
    """Walk the e-tender archive back `years` from now, committing every batch."""
    client = client or UzexClient()
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=round(years * 365.25))
    stats = BackfillStats()

    cursor = get_cursor(session, job_name)
    if restart:
        cursor.last_page = 0
    start_index = max(cursor.last_page, 0) + 1
    session.commit()  # the cursor row must survive a rolled-back batch

    # The cursor is a claim about work already done. If the rows it claims are not in the
    # table -- a wipe, a restore from an older dump, a different database -- then resuming
    # reports success while importing nothing, which is the silent gap this whole job exists
    # to avoid. Say so loudly rather than returning a clean summary over an empty table.
    imported = session.scalar(
        select(func.count()).select_from(Procedure)
        .where(Procedure.source == "uzex", Procedure.source_id.like("uzex_et_%"))
    ) or 0
    if start_index > 1 and imported < (start_index - 1) * 0.5:
        stats.cursor_mismatch = (
            f"cursor claims {start_index - 1} deals walked but only {imported} are stored; "
            f"resuming would import nothing. Re-run with restart=True to refill the gap."
        )
        log.warning("Backfill: %s", stats.cursor_mismatch)

    log.info("Backfill from index %d back to %s", start_index, cutoff.strftime("%Y-%m-%d"))

    index = start_index
    for _ in range(max_batches):
        try:
            deals = client.fetch_etender_deals(from_idx=index, to_idx=index + batch_size - 1,
                                               system_id=0)
        except Exception as exc:
            # Leave the cursor where it is: the next run retries this same batch.
            stats.stopped_because = f"fetch failed at index {index}: {exc}"
            stats.errors.append(stats.stopped_because)
            log.warning("Backfill %s", stats.stopped_because)
            return stats

        if not deals:
            stats.stopped_because = f"archive exhausted at index {index}"
            break

        records = []
        for d in deals:
            seen = _deal_date(d)
            if seen and (stats.oldest_seen is None or seen < stats.oldest_seen):
                stats.oldest_seen = seen
            try:
                records.append(parse_uzex_etender_deal(d, trade_info=None))
            except Exception as exc:
                stats.skipped += 1
                log.warning("Backfill: skipping deal %s: %s", d.get("deal_id"), exc)

        if records:
            batch = import_uzex_records(session, records)
            stats.inserted += batch.get("inserted", 0)
            stats.updated += batch.get("updated", 0)

        stats.fetched += len(deals)
        stats.batches += 1
        index += len(deals)
        cursor.last_page = index - 1
        session.commit()

        log.info("Backfill batch %d: index %d, %d deals, oldest %s, +%d new",
                 stats.batches, index, len(deals),
                 stats.oldest_seen.strftime("%Y-%m-%d") if stats.oldest_seen else "-",
                 stats.inserted)

        if stats.oldest_seen and stats.oldest_seen <= cutoff:
            stats.stopped_because = f"reached {cutoff.strftime('%Y-%m-%d')}"
            break
    else:
        stats.stopped_because = f"batch ceiling of {max_batches} reached"

    session.commit()
    log.info("%s", stats.summary())
    return stats
