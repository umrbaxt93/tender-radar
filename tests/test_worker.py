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


def test_collect_treats_a_refused_endpoint_as_no_page_not_an_empty_one():
    """A CAPTCHA wall or a withdrawn route must stop paging, not read as the last page."""
    records: list = []
    meta = worker._collect(
        records,
        "auctions p0",
        lambda: {
            "error": "HTTP 403",
            "http_status": 403,
            "message": "Captcha tekshiruvi muvaffaqiyatsiz",
            "result": {"data": [], "meta": {"totalCount": 0}},
        },
        lambda it: it,
    )
    assert meta == {}
    assert records == []


def test_sync_ebirja_pages_through_the_auction_list(monkeypatch):
    pages = {
        0: {"result": {"data": [{"id": 1}, {"id": 2}], "meta": {"pageCount": 2}}},
        1: {"result": {"data": [{"id": 3}], "meta": {"pageCount": 2}}},
    }
    asked: list[int] = []

    class Client:
        def fetch_active_auctions(self, page=0, per_page=20, search=None):
            asked.append(page)
            return pages.get(page, {"result": {"data": [], "meta": {"pageCount": 2}}})

    monkeypatch.setattr(worker, "EbirjaClient", Client)
    monkeypatch.setattr(worker, "parse_ebirja_auction", lambda row: row)
    imported: list = []
    monkeypatch.setattr(
        worker,
        "import_ebirja_records",
        lambda s, r: (imported.extend(r), {"inserted": len(r)})[1],
    )

    assert worker.sync_ebirja() == 3
    assert asked == [0, 1]
    assert [r["id"] for r in imported] == [1, 2, 3]


def test_sync_ebirja_writes_nothing_when_the_endpoint_refuses(monkeypatch):
    class Blocked:
        def fetch_active_auctions(self, page=0, per_page=20, search=None):
            return {
                "error": "HTTP 404",
                "http_status": 404,
                "message": "Page not found.",
                "result": {"data": [], "meta": {"totalCount": 0}},
            }

    monkeypatch.setattr(worker, "EbirjaClient", Blocked)
    called: list = []
    monkeypatch.setattr(worker, "import_ebirja_records", lambda *a, **k: called.append(a) or {})

    assert worker.sync_ebirja() == 0
    assert called == []


def test_deploy_error_reports_scp_stderr_with_the_remediation():
    """The old check=True hid scp's reason, leaving only "exit status 1" in the log."""
    import subprocess

    failed = subprocess.CompletedProcess(
        args=["scp"], returncode=1, stdout="", stderr="scp: Connection closed\n"
    )
    msg = worker._deploy_error(failed)
    assert "Connection closed" in msg
    assert "SSH Access" in msg

    other = subprocess.CompletedProcess(
        args=["scp"], returncode=1, stdout="", stderr="No such file or directory"
    )
    assert "SSH Access" not in worker._deploy_error(other)


def test_deploy_error_drops_the_openssh_post_quantum_advisory():
    """OpenSSH 10 prints it on every connection to an older server; it is not the failure."""
    import subprocess

    proc = subprocess.CompletedProcess(
        args=["scp"],
        returncode=255,
        stdout="",
        stderr=(
            "** WARNING: connection is not using a post-quantum key exchange algorithm.\n"
            '** This session may be vulnerable to "store now, decrypt later" attacks.\n'
            "** The server may need to be upgraded. See https://openssh.com/pq.html\n"
            "scp: Connection closed\n"
        ),
    )
    msg = worker._deploy_error(proc)
    assert msg.startswith("scp: Connection closed")
    assert "post-quantum" not in msg
    assert "SSH Access" in msg
