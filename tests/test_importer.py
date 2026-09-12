from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from radar.importer import get_cursor, run_import
from radar.models import ImportCursor, LotItem, Organization, Procedure, RawSnapshot
from radar.snapshots import sha256_hex, snapshot_body
from radar.source.client import FixtureSource, SourceError, SourcePaused


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_import_samples_and_idempotency(session, samples_dir):
    src = FixtureSource(samples_dir)
    stats = run_import(session, src)
    assert stats.pages == 1 and stats.inserted == 12 and stats.updated == 0
    assert stats.stopped_reason == "end_of_listing"
    assert count(session, Procedure) == 12
    assert count(session, RawSnapshot) == 13  # 1 list + 12 details
    assert session.get(ImportCursor, "uzex_completed").last_page == 1
    orgs = count(session, Organization)
    items = count(session, LotItem)
    # second run: cursor is at the end, nothing changes
    again = run_import(session, src)
    assert again.pages == 0 and count(session, Procedure) == 12
    # forced re-import with refresh from page 1: upserts, no duplicates
    cur = get_cursor(session)
    cur.last_page = 0
    session.commit()
    third = run_import(session, src, refresh=True)
    assert third.updated == 12 and third.inserted == 0
    assert count(session, Procedure) == 12
    assert count(session, Organization) == orgs
    assert count(session, LotItem) == items
    assert count(session, RawSnapshot) == 13  # identical bodies are not duplicated


def test_snapshot_roundtrip(session, samples_dir):
    run_import(session, FixtureSource(samples_dir))
    proc = session.scalar(select(Procedure).where(Procedure.source_id == "SYN-000001"))
    snap = session.get(RawSnapshot, proc.raw_snapshot_id)
    body = snapshot_body(snap)
    assert sha256_hex(body) == snap.sha256
    assert body == (samples_dir / "detail_SYN-000001.json").read_bytes()


def test_source_label_is_not_uzex_for_fixtures(session, samples_dir):
    run_import(session, FixtureSource(samples_dir))
    sources = set(session.scalars(select(Procedure.source)))
    assert sources == {"synthetic"}


def test_limit_and_since(session, samples_dir):
    stats = run_import(session, FixtureSource(samples_dir), limit=5)
    assert stats.inserted == 5 and stats.stopped_reason == "limit"
    get_cursor(session).last_page = 0
    session.commit()
    since = datetime(2026, 6, 1, tzinfo=UTC)
    stats = run_import(session, FixtureSource(samples_dir), since=since, refresh=True)
    assert stats.stopped_reason == "since"
    newer = [c for c in session.scalars(select(Procedure.completed_at)) if c >= since]
    assert stats.fetched_details == len(newer) and 0 < len(newer) < 12


class CrashingSource(FixtureSource):
    """Fails on the N-th detail fetch to simulate a crash mid-page."""

    def __init__(self, directory, crash_after: int, exc=SourcePaused):
        super().__init__(directory)
        self.crash_after = crash_after
        self.calls = 0
        self.exc = exc

    def detail(self, source_id):
        self.calls += 1
        if self.calls == self.crash_after:
            raise self.exc("simulated failure")
        return super().detail(source_id)


def test_resume_after_crash(session, samples_dir):
    crashing = CrashingSource(samples_dir, crash_after=5)
    stats = run_import(session, crashing)
    assert "SourcePaused" in (stats.stopped_reason or "")
    # page was rolled back: cursor untouched, nothing half-written
    session.expire_all()
    assert session.get(ImportCursor, "uzex_completed").last_page == 0
    assert count(session, Procedure) == 0
    # resume finishes the job
    stats = run_import(session, FixtureSource(samples_dir))
    assert stats.inserted == 12
    assert session.get(ImportCursor, "uzex_completed").last_page == 1


def test_unexpected_exception_propagates(session, samples_dir):
    crashing = CrashingSource(samples_dir, crash_after=3, exc=RuntimeError)
    with pytest.raises(RuntimeError):
        run_import(session, crashing)
    session.rollback()
    assert count(session, Procedure) == 0


def test_missing_fixture_dir():
    with pytest.raises(SourceError):
        FixtureSource("/nonexistent/path")
