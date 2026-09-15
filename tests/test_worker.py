"""Worker cycle resilience: a failing stage is logged and skipped, never fatal.

The daemon runs unattended under launchd, so the contract these tests pin down is that
run_once() always returns a summary. A network blip in one source, a malformed record
from another, or an unreachable deploy host must each cost only their own stage.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from radar import worker


@pytest.fixture
def wired(session, monkeypatch):
    @contextmanager
    def scope(*args, **kwargs):
        yield session

    monkeypatch.setattr(worker, "session_scope", scope)
    return session


def test_run_once_reports_every_stage(monkeypatch):
    monkeypatch.setattr(worker, "sync_ebirja", lambda: 7)
    monkeypatch.setattr(worker, "sync_uzex", lambda: 5)
    monkeypatch.setattr(worker, "refresh_renewals", lambda: 42)
    monkeypatch.setattr(worker, "rebuild_and_deploy", lambda: None)

    result = worker.run_once()

    assert result["ebirja_inserted"] == 7
    assert result["uzex_inserted"] == 5
    assert result["renewal_opportunities"] == 42
    assert result["deployed"] is True
    assert "duration_s" in result and "started_at" in result


def test_a_failing_source_does_not_stop_the_other_stages(monkeypatch):
    """The original bug: an exception in sync_ebirja skipped UZEX and the deploy entirely."""
    def boom():
        raise ConnectionError("E-Birja unreachable")

    monkeypatch.setattr(worker, "sync_ebirja", boom)
    monkeypatch.setattr(worker, "sync_uzex", lambda: 5)
    monkeypatch.setattr(worker, "refresh_renewals", lambda: 9)
    deployed = []
    monkeypatch.setattr(worker, "rebuild_and_deploy", lambda: deployed.append(True))

    result = worker.run_once()

    assert result["ebirja_inserted"] == 0
    assert result["uzex_inserted"] == 5
    assert result["renewal_opportunities"] == 9
    assert deployed == [True]


def test_run_once_survives_every_stage_failing(monkeypatch):
    for name in ("sync_ebirja", "sync_uzex", "refresh_renewals", "rebuild_and_deploy"):
        monkeypatch.setattr(worker, name, lambda: (_ for _ in ()).throw(RuntimeError("down")))

    result = worker.run_once()

    assert result["ebirja_inserted"] == 0
    assert result["uzex_inserted"] == 0
    assert result["renewal_opportunities"] == 0
    assert result["deployed"] is False


def test_a_failed_deploy_still_reports_the_ingested_rows(monkeypatch):
    monkeypatch.setattr(worker, "sync_ebirja", lambda: 3)
    monkeypatch.setattr(worker, "sync_uzex", lambda: 4)
    monkeypatch.setattr(worker, "refresh_renewals", lambda: 0)

    def scp_failed():
        raise OSError("ssh: connect to host timed out")

    monkeypatch.setattr(worker, "rebuild_and_deploy", scp_failed)

    result = worker.run_once()

    assert result["deployed"] is False
    assert (result["ebirja_inserted"], result["uzex_inserted"]) == (3, 4)


def test_collect_keeps_good_records_and_skips_a_malformed_one():
    records: list = []
    page = {"result": {"data": ["ok-1", "bad", "ok-2"]}}

    def parse(item):
        if item == "bad":
            raise ValueError("missing contract number")
        return item

    worker._collect(records, "e-shop", lambda: page, parse)

    assert records == ["ok-1", "ok-2"]


def test_collect_swallows_a_fetch_failure():
    records: list = []

    def fetch():
        raise TimeoutError("read timed out")

    worker._collect(records, "e-shop", fetch, lambda it: it)

    assert records == []


def test_sync_ebirja_returns_zero_when_the_source_is_down(monkeypatch):
    class DeadClient:
        def __getattr__(self, _name):
            def fail(*args, **kwargs):
                raise ConnectionError("no route to host")
            return fail

    monkeypatch.setattr(worker, "EbirjaClient", DeadClient)
    imported = []
    monkeypatch.setattr(worker, "import_ebirja_records",
                        lambda s, r: imported.append(r) or {"inserted": 0})

    assert worker.sync_ebirja() == 0
    # No empty write should reach the database when every page failed.
    assert imported == []


def test_deploy_is_skipped_when_unconfigured(wired, monkeypatch):
    from radar.config import Settings

    monkeypatch.setattr(worker, "load_settings", lambda: Settings(dashboard_data_path=""))
    ran = []
    monkeypatch.setattr(worker.subprocess, "run", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(worker, "generate_ai_recommendation", lambda payload: {})

    worker.rebuild_and_deploy()

    assert ran == []


def test_the_cycle_recomputes_the_radar(monkeypatch):
    """Ingestion without this stage leaves renewal_opportunity frozen at whenever someone
    last ran `radar renewal` by hand, so newly ingested IT contracts never reach the Radar."""
    monkeypatch.setattr(worker, "sync_ebirja", lambda: 0)
    monkeypatch.setattr(worker, "sync_uzex", lambda: 0)
    monkeypatch.setattr(worker, "rebuild_and_deploy", lambda: None)
    called = []
    monkeypatch.setattr(worker, "refresh_renewals", lambda: called.append(True) or 12)

    result = worker.run_once()

    assert called == [True]
    assert result["renewal_opportunities"] == 12


def test_refresh_renewals_rebuilds_from_current_classifications(wired, monkeypatch):
    monkeypatch.setattr(worker, "compute_renewals", lambda session: 5)
    assert worker.refresh_renewals() == 5
