"""Command line interface: python -m radar <command> [options]."""

from __future__ import annotations

import argparse
import json
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
        log.warning(
            "importing from FIXTURES %s (source label %r) - not live data", fixture_dir, source.name
        )
    else:
        source = HttpSource(
            settings.source_list_url,
            settings.source_detail_url,
            settings.contact_email,
            mapping=load_mapping(),
            limiter=RateLimiter(settings.request_interval_s),
        )
    with session_scope() as session:
        if args.reset_cursor:
            reset_cursor(session)
        stats = run_import(
            session,
            source,
            since=_since(args.since),
            limit=args.limit,
            refresh=args.refresh,
            match_threshold=settings.org_match_threshold,
        )
    print(
        f"import: pages={stats.pages} listed={stats.listed} details={stats.fetched_details} "
        f"inserted={stats.inserted} updated={stats.updated} "
        f"skipped={stats.skipped_existing} stopped={stats.stopped_reason} "
        f"errors={len(stats.errors)}"
    )
    return 0 if not (stats.stopped_reason or "").startswith("Source") else 3


def cmd_reparse(args: argparse.Namespace) -> int:
    from radar.importer import reparse_from_snapshots

    settings = load_settings()
    with session_scope() as session:
        stats = reparse_from_snapshots(
            session,
            limit=args.limit,
            dry_run=args.dry_run,
            match_threshold=settings.org_match_threshold,
        )
    print(stats.summary() + (" (dry run, nothing written)" if args.dry_run else ""))
    for error in stats.errors[:10]:
        print("  " + error)
    return 1 if stats.checksum_failures else 0


def cmd_worker(args: argparse.Namespace) -> int:
    from radar.worker import run_cycle, run_forever

    settings = load_settings()
    kwargs = dict(
        fixtures=args.fixtures or "",
        limit=args.limit,
        mock_ai=args.mock_ai,
        skip_import=args.skip_import,
    )
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
        if getattr(args, "recheck", False):
            from radar.classify.pipeline import recheck_classifications

            changed = recheck_classifications(session)
            print(f"classify --recheck: {changed} classifications updated with new rules")
            return 0
        report = run_classification(
            session,
            settings,
            use_ai=not args.rules_only,
            limit=args.limit,
            mock=args.mock_ai,
            refresh=args.refresh,
            unsure_only=args.unsure,
        )
    print(report.summary())
    return 0


def cmd_dedup(args: argparse.Namespace) -> int:
    from radar.dedup import find_and_merge_duplicates

    with session_scope() as session:
        res = find_and_merge_duplicates(session)
    print(f"dedup: found {res['found']} matching pairs, merged {res['merged']} procedures")
    for d in res["details"]:
        print(
            f"  merged duplicate {d['duplicate_id']} ({d['duplicate_source']}) "
            f"into primary {d['primary_id']}"
        )
    return 0


def cmd_renewal(args: argparse.Namespace) -> int:
    from radar.renewal import compute_renewals

    with session_scope() as session:
        n = compute_renewals(session, now=datetime.now(UTC))
    print(f"renewal: {n} opportunities recomputed")
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    from radar.backfill import backfill_etender

    with session_scope() as session:
        stats = backfill_etender(
            session, years=args.years, batch_size=args.batch, restart=args.restart
        )
    print(stats.summary())
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from radar.export import export_workbook

    settings = load_settings()
    with session_scope() as session:
        path, rows = export_workbook(
            session, settings.out_dir / "renewal_radar.xlsx", now=datetime.now(UTC)
        )
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


def cmd_migrate_xt(args: argparse.Namespace) -> int:
    from radar.migrate_xt import migrate_xt_lots

    settings = load_settings()
    with session_scope() as session:
        stats = migrate_xt_lots(session, sqlite_path=args.sqlite_path, settings=settings)
    print(
        f"migrate-xt: considered={stats['considered']} inserted={stats['inserted']} "
        f"updated={stats['updated']} items={stats['items']}"
    )
    return 0


def cmd_crm_timeline(args: argparse.Namespace) -> int:
    import json

    from radar.crm import get_company_profile_and_timeline

    with session_scope() as session:
        data = get_company_profile_and_timeline(session, args.stir)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0 if data.get("found") else 1


def cmd_crm_proposal(args: argparse.Namespace) -> int:
    import json

    from radar.crm import generate_grounded_proposal

    with session_scope() as session:
        data = generate_grounded_proposal(session, args.stir)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0 if "error" not in data else 1


def cmd_crm_deal(args: argparse.Namespace) -> int:
    from radar.crm import push_deal_for_procedure

    with session_scope() as session:
        res = push_deal_for_procedure(
            session=session,
            procedure_id=args.procedure_id,
            title=args.title,
            amount=args.amount,
            use_mock=args.mock,
        )
    print(
        f"crm-deal: status={res['status']} created={res['created']} "
        f"deal_id={res['deal_id']} amount={res.get('amount')}"
    )
    print(f"  message: {res['message']}")
    return 0


def cmd_users(args: argparse.Namespace) -> int:
    from sqlalchemy import select

    from radar.auth import hash_password
    from radar.models import User

    subcmd = getattr(args, "users_action", None)
    if subcmd == "create":
        username = args.username.strip()
        role = args.role.strip().lower()
        if role not in ("admin", "sales", "viewer"):
            print(f"Error: Invalid role '{role}'. Must be one of: admin, sales, viewer")
            return 1
        password = args.password
        if not password:
            import getpass

            password = getpass.getpass(f"Password for {username}: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Error: Passwords do not match")
                return 1
        if len(password) < 8:
            print("Error: Password must be at least 8 characters long")
            return 1

        pwd_hash = hash_password(password)
        with session_scope() as session:
            existing = session.scalar(select(User).where(User.username == username))
            if existing:
                print(f"User '{username}' already exists. Updating role and password...")
                existing.role = role
                existing.password_hash = pwd_hash
                existing.is_active = True
            else:
                new_user = User(
                    username=username,
                    password_hash=pwd_hash,
                    role=role,
                    is_active=True,
                )
                session.add(new_user)
            session.commit()
        print(f"User '{username}' with role '{role}' saved successfully.")
        return 0

    elif subcmd == "list":
        with session_scope() as session:
            users = session.scalars(select(User).order_by(User.id)).all()
            print(f"Total users: {len(users)}")
            for u in users:
                status = "ACTIVE" if u.is_active else "DISABLED"
                last = u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "Never"
                print(
                    f"  [{u.id}] {u.username:<16} role={u.role:<8} status={status:<8} last={last}"
                )
        return 0

    print("Usage: python -m radar users {create,list}")
    return 1


def cmd_crm_push(args: argparse.Namespace) -> int:
    from radar.crm import push_to_bitrix24

    with session_scope() as session:
        res = push_to_bitrix24(
            session=session,
            target=args.target,
            title=args.title,
            amount=args.amount or 0.0,
            use_mock=args.mock,
        )
    print(
        f"crm-push: success={res['success']} deal_id={res.get('bitrix_deal_id')} "
        f"already_existed={res.get('already_existed')}"
    )
    print(f"  message: {res['message']}")
    return 0 if res.get("success") else 1


def cmd_health(args: argparse.Namespace) -> int:
    from sqlalchemy import text

    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    print("db: ok")
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    from radar.cleanup import cleanup_old_snapshots, parse_retention_period

    try:
        days = parse_retention_period(args.older_than)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    with session_scope() as session:
        stats = cleanup_old_snapshots(session, older_than_days=days)
        session.commit()

    print(
        f"cleanup: deleted {stats['deleted_snapshots']} raw snapshots "
        f"older than {stats['older_than_days']} days (cutoff: {stats['cutoff']})"
    )
    return 0


def cmd_alert(args: argparse.Namespace) -> int:
    from radar.alerts.telegram import send_hot_opportunity_alerts

    settings = load_settings()
    with session_scope() as session:
        stats = send_hot_opportunity_alerts(
            session=session,
            settings=settings,
            min_score=args.min_score,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    print(
        f"alerts: considered={stats['considered']} sent={stats['sent']} "
        f"errors={stats['errors']} (recipient={stats['recipient']}, min_score={stats['min_score']})"
    )
    return 0 if stats["errors"] == 0 else 1


def cmd_migrate_sqlite(args: argparse.Namespace) -> int:
    from radar.migration import migrate_all_sqlite

    with session_scope() as session:
        stats = migrate_all_sqlite(session, sqlite_path=args.sqlite_path)
    print(
        f"migrate-sqlite: companies={stats['companies_synced']}, "
        f"lots_considered={stats['lots_considered']}, "
        f"inserted={stats['procedures_inserted']}, "
        f"updated={stats['procedures_updated']}, "
        f"items={stats['items_migrated']}, "
        f"awards={stats['awards_migrated']}, "
        f"classifications={stats['classifications_migrated']}"
    )
    return 0


def cmd_advisor(args: argparse.Namespace) -> int:
    from radar.ai_advisor import (
        format_lot_recommendation,
        format_macro_strategy,
        generate_macro_business_strategy,
        get_recommendation_for_procedure,
    )

    with session_scope() as session:
        if args.macro or not args.procedure_id:
            strat = generate_macro_business_strategy(session)
            if args.format == "json":
                print(json.dumps(strat, indent=2, ensure_ascii=False))
            else:
                print(format_macro_strategy(strat))
            return 0

        rec = get_recommendation_for_procedure(session, args.procedure_id)
        if "error" in rec:
            print(f"Error: {rec['error']}", file=sys.stderr)
            return 1
        if args.format == "json":
            print(json.dumps(rec, indent=2, ensure_ascii=False))
        else:
            print(format_lot_recommendation(rec))
        return 0


def cmd_bot(args: argparse.Namespace) -> int:
    from radar.alerts.bot import TelegramBotDispatcher
    from radar.alerts.telegram import get_telegram_client

    settings = load_settings()
    client = get_telegram_client(settings)
    dispatcher = TelegramBotDispatcher(client, settings)

    if args.once:
        count = dispatcher.poll_once()
        print(f"bot: processed {count} updates in single poll.")
        return 0

    print(
        f"bot: starting Telegram listener for chat_id={settings.telegram_chat_id or 'mock/all'}..."
    )
    dispatcher.run_forever(interval_s=args.interval)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m radar", description="Tender Radar MVP")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("users", help="manage system users and roles")
    u_sub = s.add_subparsers(dest="users_action", required=True)
    c_p = u_sub.add_parser("create", help="create or update user")
    c_p.add_argument("--username", required=True, help="unique username")
    c_p.add_argument(
        "--role", required=True, choices=["admin", "sales", "viewer"], help="user role"
    )
    c_p.add_argument("--password", help="optional password (will prompt if not provided)")
    u_sub.add_parser("list", help="list existing users")
    s.set_defaults(func=cmd_users)

    s = sub.add_parser("migrate", help="apply Alembic migrations")
    s.set_defaults(func=cmd_migrate)

    s = sub.add_parser("migrate-xt", help="migrate verified real XT-Xarid lots from SQLite")
    s.add_argument("--sqlite-path", default=None, help="path to SQLite softy_procurement.db")
    s.set_defaults(func=cmd_migrate_xt)

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
    s.add_argument(
        "--recheck",
        action="store_true",
        help="re-evaluate existing classifications with updated rules",
    )
    s.add_argument("--limit", type=int)
    s.add_argument(
        "--unsure",
        action="store_true",
        help="only lots the rules abstained on (the rows AI can actually inform)",
    )
    s.set_defaults(func=cmd_classify)

    s = sub.add_parser("renewal", help="recompute renewal opportunities")
    s.set_defaults(func=cmd_renewal)

    s = sub.add_parser("dedup", help="find and merge duplicate procedures across sources")
    s.set_defaults(func=cmd_dedup)

    s = sub.add_parser("backfill", help="walk the UZEX e-tender archive back N years")
    s.add_argument("--years", type=float, default=3.0, help="how far back to go (default 3)")
    s.add_argument("--batch", type=int, default=500, help="deals per request (default 500)")
    s.add_argument("--restart", action="store_true", help="ignore the saved cursor")
    s.set_defaults(func=cmd_backfill)

    s = sub.add_parser("export", help="write out/renewal_radar.xlsx")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("web", help="serve /radar and /health")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_web)

    s = sub.add_parser("stats", help="print database counts")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("crm-timeline", help="get company timeline for STIR")
    s.add_argument("stir", help="taxpayer identification number (STIR)")
    s.set_defaults(func=cmd_crm_timeline)

    s = sub.add_parser("crm-proposal", help="generate grounded proposal draft for STIR")
    s.add_argument("stir", help="taxpayer identification number (STIR)")
    s.set_defaults(func=cmd_crm_proposal)

    s = sub.add_parser("crm-deal", help="create Bitrix24 deal for procedure (idempotent)")
    s.add_argument("procedure_id", type=int, help="procedure ID")
    s.add_argument("--title", help="optional custom deal title")
    s.add_argument("--amount", type=float, help="optional custom amount")
    s.add_argument("--mock", action="store_true", help="force mock mode")
    s.set_defaults(func=cmd_crm_deal)

    s = sub.add_parser("crm-push", help="push deal for company STIR or procedure ID (idempotent)")
    s.add_argument("target", help="company STIR or procedure ID")
    s.add_argument("--title", help="optional custom deal title")
    s.add_argument("--amount", type=float, default=0.0, help="optional custom amount")
    s.add_argument("--mock", action="store_true", help="force mock mode")
    s.set_defaults(func=cmd_crm_push)

    s = sub.add_parser("health", help="check database connectivity")
    s.set_defaults(func=cmd_health)

    s = sub.add_parser("cleanup", help="cleanup snapshots by retention policy")
    s.add_argument(
        "--older-than",
        default="365d",
        help="retention period threshold, e.g. '365d' or '1y' (default: 365d)",
    )
    s.set_defaults(func=cmd_cleanup)

    s = sub.add_parser("alert", help="send Telegram alerts for hot renewal opportunities")
    s.add_argument(
        "--min-score",
        type=int,
        default=None,
        help="minimum score threshold (default from env or 80)",
    )
    s.add_argument("--limit", type=int, default=20, help="max alerts to dispatch (default 20)")
    s.add_argument(
        "--dry-run", action="store_true", help="preview formatted alerts without sending"
    )
    s.set_defaults(func=cmd_alert)

    s = sub.add_parser("migrate-sqlite", help="migrate all historical lots from SQLite")
    s.add_argument(
        "--sqlite-path",
        default=None,
        help="optional custom path to SQLite softy_procurement.db",
    )
    s.set_defaults(func=cmd_migrate_sqlite)

    s = sub.add_parser("advisor", help="generate AI business and procurement advice")
    s.add_argument("--procedure-id", type=int, default=None, help="procedure ID for specific lot")
    s.add_argument("--macro", action="store_true", help="generate macro market strategy")
    s.add_argument("--format", choices=["text", "json"], default="text", help="output format")
    s.set_defaults(func=cmd_advisor)

    s = sub.add_parser("bot", help="run interactive Telegram Bot listener daemon")
    s.add_argument("--interval", type=float, default=2.0, help="polling interval in seconds")
    s.add_argument("--once", action="store_true", help="poll once and exit (for cron/worker)")
    s.set_defaults(func=cmd_bot)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
