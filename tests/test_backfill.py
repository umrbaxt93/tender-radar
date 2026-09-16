"""Archive backfill: resumable, bounded by date, and never a per-deal detail call."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from radar.backfill import backfill_etender
from radar.importer import get_cursor

NOW = datetime(2026, 9, 15, tzinfo=UTC)
JOB = "test_backfill"


def deal(n: int, date: str) -> dict:
    """One e-tender list row, carrying everything the ten-column export needs."""
    return {
        "deal_id": n,
        "trade_id": 900000 + n,
        "display_no": f"D{n}",
        "category_name": "Kompyuter texnikasi",
        "customer_name": f"Buyurtmachi {n}",
        "customer_inn": f"30{n:07d}",
        "provider_name": f"Yetkazib beruvchi {n}",
        "provider_inn": f"31{n:07d}",
        "start_cost": 1000.0,
        "deal_cost": 950.0,
        "deal_date": f"{date}T10:00:00",
        "deal_contract_date": None,
    }


class FakeClient:
    """Serves a fixed archive, newest first, and records every call made."""

    def __init__(self, deals: list[dict], fail_at: int | None = None) -> None:
        self.deals = deals
        self.fail_at = fail_at
        self.calls: list[tuple[int, int]] = []
        self.detail_calls = 0

    def fetch_etender_deals(self, from_idx: int, to_idx: int, system_id: int = 0) -> list[dict]:
        self.calls.append((from_idx, to_idx))
        if self.fail_at is not None and from_idx >= self.fail_at:
            raise ConnectionError("read timed out")
        return self.deals[from_idx - 1: to_idx]

    def fetch_etender_trade_detail(self, trade_id):  # pragma: no cover - must never run
        self.detail_calls += 1
        raise AssertionError("the backfill must not fetch per-deal details")


@pytest.fixture
def archive() -> list[dict]:
    # 30 deals, one per month going back from 2026-09, so 3 years is not reached.
    out = []
    y, m = 2026, 9
    for i in range(1, 31):
        out.append(deal(i, f"{y:04d}-{m:02d}-05"))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def test_backfill_walks_the_archive_and_never_opens_a_deal(session, archive):
    client = FakeClient(archive)
    stats = backfill_etender(session, client, years=3, batch_size=10, now=NOW, job_name=JOB)

    assert stats.fetched == 30
    assert stats.inserted == 30
    assert client.detail_calls == 0
    assert stats.stopped_because.startswith("archive exhausted")


def test_backfill_stops_once_it_reaches_the_cutoff(session, archive):
    client = FakeClient(archive)
    stats = backfill_etender(session, client, years=1, batch_size=10, now=NOW, job_name=JOB)

    # One year back is 12 deals in, so the second batch crosses it and the third never runs.
    assert stats.batches == 2
    assert stats.fetched == 20
    assert stats.stopped_because == "reached 2025-09-15"


def test_an_interrupted_backfill_resumes_where_it_stopped(session, archive):
    first = FakeClient(archive, fail_at=11)
    stats = backfill_etender(session, first, years=3, batch_size=10, now=NOW, job_name=JOB)
    assert stats.fetched == 10
    assert "fetch failed" in stats.stopped_because

    second = FakeClient(archive)
    resumed = backfill_etender(session, second, years=3, batch_size=10, now=NOW, job_name=JOB)

    # It picks up at 11, not at 1: the first ten are not fetched twice.
    assert second.calls[0] == (11, 20)
    assert resumed.fetched == 20
    assert resumed.inserted == 20


def test_a_failed_batch_leaves_the_cursor_on_that_batch(session, archive):
    client = FakeClient(archive, fail_at=11)
    backfill_etender(session, client, years=3, batch_size=10, now=NOW, job_name=JOB)

    assert get_cursor(session, JOB).last_page == 10


def test_restart_ignores_the_saved_cursor(session, archive):
    backfill_etender(session, FakeClient(archive), years=3, batch_size=10, now=NOW, job_name=JOB)
    again = FakeClient(archive)
    backfill_etender(session, again, years=3, batch_size=10, now=NOW, job_name=JOB, restart=True)

    assert again.calls[0] == (1, 10)


def test_a_malformed_deal_is_skipped_not_fatal(session, archive):
    broken = list(archive)
    broken[3] = {"deal_id": None, "deal_date": "2026-06-05T10:00:00"}
    stats = backfill_etender(session, FakeClient(broken), years=3, batch_size=10, now=NOW,
                             job_name=JOB)

    assert stats.fetched == 30
    assert stats.inserted + stats.skipped == 30


def test_the_list_row_alone_fills_customer_and_winner_stir(session, archive):
    from sqlalchemy import select

    from radar.models import Award, Organization, Procedure

    backfill_etender(session, FakeClient(archive[:10]), years=3, batch_size=10, now=NOW,
                     job_name=JOB)

    proc = session.scalar(select(Procedure).where(Procedure.source_id == "uzex_et_1"))
    assert proc is not None
    customer = session.get(Organization, proc.customer_org_id)
    award = session.get(Award, proc.id)
    winner = session.get(Organization, award.supplier_org_id)

    assert customer.stir == "300000001"
    assert winner.stir == "310000001"
    assert award.amount is not None


def test_a_cursor_ahead_of_the_data_is_reported_not_ignored(session, archive):
    """The cursor is a claim about work already done. After a wipe it still claims it, so a
    resume imports nothing and reports success over an empty table — the exact silent gap
    this job exists to prevent."""
    from sqlalchemy import delete

    from radar.models import Procedure

    backfill_etender(session, FakeClient(archive), years=3, batch_size=10, now=NOW, job_name=JOB)
    assert get_cursor(session, JOB).last_page == 30

    # The data goes away; the cursor does not.
    session.execute(delete(Procedure).where(Procedure.source == "uzex"))
    session.commit()

    stats = backfill_etender(session, FakeClient(archive), years=3, batch_size=10, now=NOW,
                             job_name=JOB)

    assert stats.cursor_mismatch is not None
    assert "30 deals walked" in stats.cursor_mismatch
    assert "restart=True" in stats.cursor_mismatch
    assert "WARNING" in stats.summary()


def test_no_mismatch_warning_when_the_data_is_there(session, archive):
    stats = backfill_etender(session, FakeClient(archive), years=3, batch_size=10, now=NOW,
                             job_name=JOB)
    assert stats.cursor_mismatch is None
    assert "WARNING" not in stats.summary()
