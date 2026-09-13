"""Command line interface: python -m radar <command> [options]."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

from radar.config import ROOT, load_settings
from radar.db import get_engine, session_scope

log = logging.getLogger("radar")


def _since(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def cmd_import(args: argparse.Namespace) -> int:
    from radar.importer import reset_cursor, run_import
    from radar.source.client import FixtureSource, HttpSource, RateLimiter
    from radar.source.parser import load_mapping

    settings = load_settings()
    fixture_dir = args.fixtures or settings.source_fixture_dir
    if fixture_dir:
        source = FixtureSource(fixture_dir, name=args.source_name or "synthetic")
        log.warning("importing from FIXTURES %s (source label %r) - not live data",
                    fixture_dir, source.name)
    else:
        source = HttpSource(settings.source_list_url, settings.source_detail_url,
                            settings.contact_email, mapping=load_mapping(),
                            limiter=RateLimiter(settings.request_interval_s))
    with session_scope() as session:
        if args.reset_cursor:
            reset_cursor(session)
        stats = run_import(session, source, since=_since(args.since), limit=args.limit,
                           refresh=args.refresh,
                           match_threshold=settings.org_match_threshold)
    print(f"import: pages={stats.pages} listed={stats.listed} details={stats.fetched_details} "
          f"inserted={stats.inserted} updated={stats.updated} "
          f"skipped={stats.skipped_existing} stopped={stats.stopped_reason} "
          f"errors={len(stats.errors)}")
    return 0 if not (stats.stopped_reason or "").startswith("Source") else 3


def cmd_reparse(args: argparse.Namespace) -> int:
    from radar.importer import reparse_from_snapshots

    settings = load_settings()
    with session_scope() as session:
        stats = reparse_from_snapshots(session, limit=args.limit, dry_run=args.dry_run,
                                       match_threshold=settings.org_match_threshold)
    print(stats.summary() + (" (dry run, nothing written)" if args.dry_run else ""))
    for error in stats.errors[:10]:
        print("  " + error)
    return 1 if stats.checksum_failures else 0


def cmd_worker(args: argparse.Namespace) -> int:
    from radar.worker import run_cycle, run_forever

    settings = load_settings()
    kwargs = dict(fixtures=args.fixtures or "", limit=args.limit, mock_ai=args.mock_ai,
                  skip_import=args.skip_import)
    if args.interval:
        run_forever(settings, interval_s=args.interval, **kwargs)
        return 0
    result = run_cycle(settings, **kwargs)
    print(result.summary())
    return 1 if result.failed_step else 0


def cmd_classify(args: argparse.Namespace) -> int:
    from radar.classify.pipeline import run_classification

    settings = load_settings()
    with session_scope() as session:
        report = run_classification(session, settings, use_ai=not args.rules_only,
                                    limit=args.limit, mock=args.mock_ai,
                                    refresh=args.refresh)
    print(report.summary())
    return 0


def cmd_renewal(args: argparse.Namespace) -> int:
    from radar.renewal import compute_renewals

    with session_scope() as session:
        n = compute_renewals(session, now=datetime.now(UTC))
    print(f"renewal: {n} opportunities recomputed")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from radar.export import export_workbook

    settings = load_settings()
    with session_scope() as session:
        path, rows = export_workbook(session, settings.out_dir / "renewal_radar.xlsx",
                                     now=datetime.now(UTC))
    print(f"export: {path} ({rows} radar rows)")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("radar.web:app", host=args.host, port=args.port, workers=1)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from radar.stats import collect_stats

    with session_scope() as session:
        for key, value in collect_stats(session).items():
            print(f"{key}: {value}")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    from alembic.config import Config

    from alembic import command

    load_settings().require_database()
    cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    from sqlalchemy import text

    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    print("db: ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m radar", description="Tender Radar MVP")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("migrate", help="apply Alembic migrations")
    s.set_defaults(func=cmd_migrate)

    s = sub.add_parser("import", help="import completed procedures")
    s.add_argument("--since", help="YYYY-MM-DD; stop at older lots")
    s.add_argument("--limit", type=int, help="stop after N procedures")
    s.add_argument("--fixtures", help="fixture directory instead of the live source")
    s.add_argument("--source-name", help="source label for fixture imports (default synthetic)")
    s.add_argument("--refresh", action="store_true", help="re-fetch existing procedures")
    s.add_argument("--reset-cursor", action="store_true", help="start from page 1")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("reparse", help="rebuild rows from stored snapshots, no network")
    s.add_argument("--limit", type=int)
    s.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    s.set_defaults(func=cmd_reparse)

    s = sub.add_parser("worker", help="run one full cycle, or repeat on an interval")
    s.add_argument("--interval", type=float, help="seconds between cycles; omit to run once")
    s.add_argument("--fixtures", help="fixture directory instead of the live source")
    s.add_argument("--limit", type=int)
    s.add_argument("--mock-ai", action="store_true")
    s.add_argument("--skip-import", action="store_true")
    s.set_defaults(func=cmd_worker)

    s = sub.add_parser("classify", help="rules then Gemini classification")
    s.add_argument("--rules-only", action="store_true")
    s.add_argument("--mock-ai", action="store_true", help="deterministic offline mock model")
    s.add_argument("--refresh", action="store_true", help="re-classify already classified lots")
    s.add_argument("--limit", type=int)
    s.set_defaults(func=cmd_classify)

    s = sub.add_parser("renewal", help="recompute renewal opportunities")
    s.set_defaults(func=cmd_renewal)

    s = sub.add_parser("export", help="write out/renewal_radar.xlsx")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("web", help="serve /radar and /health")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_web)

    s = sub.add_parser("stats", help="print database counts")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("health", help="check database connectivity")
    s.set_defaults(func=cmd_health)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
