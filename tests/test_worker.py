"""The single worker process: one ordered cycle, stopping cleanly on failure."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from radar import worker
from radar.config import Settings
from radar.source.client import SourceError

NOW = datetime(2026, 9, 13, tzinfo=UTC)


@pytest.fixture
def wired(session, monkeypatch, tmp_path):
    @contextmanager
    def scope(*args, **kwargs):
        yield session

    monkeypatch.setattr(worker, "session_scope", scope)
    return Settings(database_url="", contact_email="ops@example.invalid", gemini_api_key="",
                    gemini_model="", classifier_budget_usd=10.0, out_dir=tmp_path)


def test_full_cycle_runs_every_step_in_order(wired, samples_dir):
    result = worker.run_cycle(wired, fixtures=str(samples_dir), mock_ai=True, now=NOW)
    assert list(result.steps) == ["import", "classify", "renewal", "export"]
    assert result.failed_step is None
    assert "new" in result.steps["import"]
    assert "rule" in result.steps["classify"]
    assert (wired.out_dir / "renewal_radar.xlsx").is_file()
    assert "cycle 2026-09-13" in result.summary()


def test_cycle_stops_when_the_source_is_not_configured(wired):
    result = worker.run_cycle(wired, now=NOW)
    assert result.failed_step == "import"
    assert "not configured" in result.steps["import"]
    assert "classify" not in result.steps


def test_cycle_stops_when_the_budget_is_spent(wired, samples_dir, monkeypatch):
    broke = Settings(database_url="", contact_email="ops@example.invalid", gemini_api_key="",
                     gemini_model="", classifier_budget_usd=0.0000001,
                     out_dir=wired.out_dir)
    result = worker.run_cycle(broke, fixtures=str(samples_dir), mock_ai=True, now=NOW)
    assert result.failed_step == "classify"
    assert "renewal" not in result.steps


def test_skip_import_runs_the_rest(wired, samples_dir):
    worker.run_cycle(wired, fixtures=str(samples_dir), mock_ai=True, now=NOW)
    result = worker.run_cycle(wired, skip_import=True, mock_ai=True, now=NOW)
    assert "import" not in result.steps and result.failed_step is None
    assert "opportunities" in result.steps["renewal"]


def test_build_source_refuses_an_unconfigured_live_source(wired):
    with pytest.raises(SourceError):
        worker.build_source(wired)


def test_run_forever_finishes_the_cycle_then_stops(wired, samples_dir, monkeypatch, capsys):
    cycles = []

    def fake_cycle(settings, **kwargs):
        cycles.append(kwargs)
        result = worker.CycleResult(started_at=NOW)
        result.steps["import"] = "0 new"
        # A signal arriving mid-cycle must not cut the cycle short.
        stopper._handle(15, None)
        return result

    stopper = worker.Stopper()
    monkeypatch.setattr(worker, "Stopper", lambda: stopper)
    monkeypatch.setattr(worker, "run_cycle", fake_cycle)
    slept = []
    worker.run_forever(wired, interval_s=99, sleep=slept.append, mock_ai=True)
    assert len(cycles) == 1 and slept == []
    assert "cycle 2026-09-13" in capsys.readouterr().out


def test_run_forever_repeats_until_stopped(wired, monkeypatch):
    calls = {"n": 0}
    stopper = worker.Stopper()

    def fake_cycle(settings, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            stopper.stop = True
        return worker.CycleResult(started_at=NOW)

    monkeypatch.setattr(worker, "Stopper", lambda: stopper)
    monkeypatch.setattr(worker, "run_cycle", fake_cycle)
    worker.run_forever(wired, interval_s=2, sleep=lambda s: None)
    assert calls["n"] == 3


def test_a_stop_while_idle_does_not_start_another_cycle(wired, monkeypatch):
    """A signal arriving during the wait must not buy one more full cycle of work."""
    calls = {"n": 0}
    stopper = worker.Stopper()

    def fake_cycle(settings, **kwargs):
        calls["n"] += 1
        return worker.CycleResult(started_at=NOW)

    slept = []

    def sleep(seconds):
        slept.append(seconds)
        if len(slept) == 3:      # the signal lands part way through the idle period
            stopper.stop = True

    monkeypatch.setattr(worker, "Stopper", lambda: stopper)
    monkeypatch.setattr(worker, "run_cycle", fake_cycle)
    worker.run_forever(wired, interval_s=3600, sleep=sleep)
    assert calls["n"] == 1
    # It stopped after about three seconds of a one hour wait, not after the full hour.
    assert sum(slept) <= 5


def test_wait_sleeps_in_slices_and_never_overshoots():
    stopper = worker.Stopper()
    slept = []
    stopper.wait(2.5, sleep=slept.append, slice_s=1.0)
    assert slept == [1.0, 1.0, 0.5]
    stopper.stop = True
    slept.clear()
    stopper.wait(60, sleep=slept.append)
    assert slept == []
