"""Single worker process running the job cycle (docs/SPEC.md: one worker.py, no brokers).

One cycle is: import -> classify -> renewal -> export. Steps run in order in one process;
there are no threads, no queue and no second connection. A failing step stops the cycle and
is reported, because a Radar built on a half-finished import would be misleading.
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from radar.classify.pipeline import run_classification
from radar.config import Settings, load_settings
from radar.db import session_scope
from radar.export import export_workbook
from radar.importer import run_import
from radar.renewal import compute_renewals
from radar.source.client import FixtureSource, HttpSource, RateLimiter, SourceError
from radar.source.parser import load_mapping

log = logging.getLogger(__name__)


@dataclass
class CycleResult:
    started_at: datetime
    steps: dict[str, str] = field(default_factory=dict)
    failed_step: str | None = None

    def summary(self) -> str:
        head = f"cycle {self.started_at:%Y-%m-%d %H:%M UTC}"
        body = "; ".join(f"{name}: {value}" for name, value in self.steps.items())
        tail = f" FAILED at {self.failed_step}" if self.failed_step else ""
        return f"{head} | {body}{tail}"


def build_source(settings: Settings, fixtures: str = ""):
    """Fixtures when asked for, otherwise the live source. Never both, never a guess."""
    fixtures = fixtures or settings.source_fixture_dir
    if fixtures:
        log.warning("worker reading FIXTURES %s - not live data", fixtures)
        return FixtureSource(fixtures)
    return HttpSource(settings.source_list_url, settings.source_detail_url,
                      settings.contact_email, mapping=load_mapping(),
                      limiter=RateLimiter(settings.request_interval_s))


def run_cycle(settings: Settings | None = None, *, fixtures: str = "", limit: int | None = None,
              mock_ai: bool = False, use_ai: bool = True, skip_import: bool = False,
              now: datetime | None = None) -> CycleResult:
    settings = settings or load_settings()
    result = CycleResult(started_at=now or datetime.now(UTC))

    if not skip_import:
        try:
            source = build_source(settings, fixtures)
        except SourceError as exc:
            result.steps["import"] = f"not configured: {exc}"
            result.failed_step = "import"
            return result
        with session_scope() as session:
            stats = run_import(session, source, limit=limit,
                               match_threshold=settings.org_match_threshold)
        result.steps["import"] = (f"{stats.inserted} new, {stats.updated} updated, "
                                  f"stopped={stats.stopped_reason}")
        if (stats.stopped_reason or "").startswith("Source"):
            result.failed_step = "import"
            return result

    with session_scope() as session:
        report = run_classification(session, settings, use_ai=use_ai, mock=mock_ai)
    result.steps["classify"] = (f"{report.by_rule} rule, {report.by_model} model, "
                                f"${report.cost_usd:.6f}")
    if (report.stopped_reason or "").startswith(("budget_exceeded", "pricing_unavailable")):
        result.failed_step = "classify"
        return result

    with session_scope() as session:
        count = compute_renewals(session, now=result.started_at)
    result.steps["renewal"] = f"{count} opportunities"

    with session_scope() as session:
        path, rows = export_workbook(session, settings.out_dir / "renewal_radar.xlsx",
                                     now=result.started_at)
    result.steps["export"] = f"{rows} radar rows -> {path}"
    return result


class Stopper:
    """Finishes the cycle in flight, then stops. No job is cut in half by a signal."""

    def __init__(self) -> None:
        self.stop = False
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle)

    def _handle(self, signum, frame) -> None:  # noqa: ARG002
        log.info("signal %s received; finishing the current cycle", signum)
        self.stop = True


def run_forever(settings: Settings | None = None, *, interval_s: float = 3600,
                sleep=time.sleep, **cycle_kwargs) -> None:
    settings = settings or load_settings()
    stopper = Stopper()
    while True:
        result = run_cycle(settings, **cycle_kwargs)
        print(result.summary(), flush=True)
        if stopper.stop:
            log.info("worker stopping after a completed cycle")
            return
        sleep(interval_s)
