"""Autonomous background worker for Tender Radar.
Periodically fetches new contracts from E-Birja, updates PostgreSQL DB,
regenerates the web dashboard, and deploys to tender.softy.uz.
"""

import datetime
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from radar.ai_advisor import generate_ai_recommendation
from radar.config import load_settings
from radar.db import session_scope
from radar.models import Classification, Organization, Procedure
from radar.renewal import compute_renewals, radar_rows
from radar.search import (
    search_competitor_intelligence,
    search_customer_intelligence,
    search_keywords,
)
from radar.source.ebirja import (
    EbirjaClient,
    import_ebirja_records,
    parse_ebirja_auction,
)
from radar.source.uzex import (
    UzexClient,
    import_uzex_records,
    parse_uzex_auction_deal,
    parse_uzex_direct_purchase,
    parse_uzex_etender_deal,
)

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "logs" / "worker.log"
# The dashboard embeds its rows in the HTML, so this is a browser limit, not a data one:
# ~600 bytes a row means the full 76k awarded contracts would be a 47 MB page. The cap is
# therefore real and permanent -- but it must never be silent, so the count that did not
# fit is written into stats and the log. The Excel export carries every row.
EXPORT_ROW_LIMIT = 10000
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("radar.worker")


def _collect(records: list, label: str, fetch, parse) -> dict:
    """Fetch one E-Birja page and parse it. A failure here skips the page, never the run.

    Returns the page's `meta` so the caller can page, and an empty dict when the page did not
    arrive -- a fetch that raised, or an endpoint that refused us. Paging on that empty dict
    stops, which is why a refusal can never be mistaken for the last page.
    """
    try:
        res = fetch()
    except Exception as exc:
        log.warning("E-Birja %s fetch failed: %s", label, exc)
        return {}
    if res.get("http_status"):
        log.error(
            "E-Birja %s refused: HTTP %s%s",
            label,
            res["http_status"],
            f" ({res['message']})" if res.get("message") else "",
        )
        return {}
    result = res.get("result") or {}
    for it in result.get("data") or []:
        try:
            rec = parse(it)
        except Exception as exc:
            log.warning("E-Birja %s: skipping malformed record: %s", label, exc)
            continue
        if rec is not None:
            records.append(rec)
    return result.get("meta") or {}


# One live auction page is 10 rows by default and the whole list has held ~14, so this ceiling
# only exists to stop a paging bug from walking the source forever.
EBIRJA_AUCTION_PER_PAGE = 50
EBIRJA_AUCTION_MAX_PAGES = 10


def sync_ebirja() -> int:
    """Import E-Birja auctions that are still open for bidding.

    E-Birja's contract list stopped being a usable public source (radar/source/ebirja.py records
    the status measured for each endpoint): one route was withdrawn and the other two now sit
    behind a CAPTCHA, which CLAUDE.md forbids working around. Calling them every cycle only
    produced 404s, 403s and a zero, so this step reads the auction endpoint, which is still
    served. Completed E-Birja contracts now arrive only through a cabinet export file.
    """
    log.info("Starting E-Birja synchronization (live auctions)...")
    client = EbirjaClient()
    records: list = []

    page = 0
    pages = 1
    while page < min(pages, EBIRJA_AUCTION_MAX_PAGES):
        meta = _collect(
            records,
            f"auctions p{page}",
            lambda p=page: client.fetch_active_auctions(
                page=p, per_page=EBIRJA_AUCTION_PER_PAGE
            ),
            parse_ebirja_auction,
        )
        if not meta:
            break
        pages = int(meta.get("pageCount") or 1)
        page += 1

    if not records:
        log.warning("E-Birja returned no usable records this cycle.")
        return 0

    with session_scope() as session:
        stats = import_ebirja_records(session, records)
        log.info("E-Birja auction import result: %s", stats)
        return stats.get("inserted", 0)


EBIRJA_EXPORT_MARKER = BASE_DIR / "out" / ".ebirja_export_imported_mtime"
EBIRJA_EXPORT_DIR = BASE_DIR / "data" / "ebirja"
EBIRJA_EXPORT_SUFFIXES = (".xlsx", ".xlsm", ".csv", ".tsv")


def ebirja_export_path() -> Path | None:
    """The cabinet export to import, or None when the owner has not left one.

    `EBIRJA_EXPORT_PATH` names an exact file. With it unset the newest export-shaped file in
    data/ebirja/ is taken, so dropping the cabinet download into that folder is enough whatever
    the cabinet chose to call it. Excel's own `~$` lock files are not export files.
    """
    explicit = os.environ.get("EBIRJA_EXPORT_PATH", "").strip()
    if explicit:
        path = Path(os.path.expanduser(explicit))
        return path if path.is_file() else None
    if not EBIRJA_EXPORT_DIR.is_dir():
        return None
    files = [
        f
        for f in EBIRJA_EXPORT_DIR.iterdir()
        if f.is_file()
        and f.suffix.lower() in EBIRJA_EXPORT_SUFFIXES
        and not f.name.startswith("~$")
    ]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def sync_ebirja_export() -> int:
    """Import an E-Birja cabinet export when the owner has left a newer one.

    E-Birja's contract endpoints are closed -- one withdrawn, two behind a CAPTCHA -- so this
    file is the only authorised route to contract history (CLAUDE.md). The download is manual;
    this step only reads what it finds. Disable with EBIRJA_EXPORT_IMPORT=0.
    """
    if os.environ.get("EBIRJA_EXPORT_IMPORT", "1").strip() == "0":
        log.info("ebirja-export: import disabled (EBIRJA_EXPORT_IMPORT=0)")
        return 0
    from radar.source.ebirja_export import import_ebirja_export, load_ebirja_export

    path = ebirja_export_path()
    if path is None:
        log.info("ebirja-export: no export file in %s; nothing to import", EBIRJA_EXPORT_DIR)
        return 0
    mtime = path.stat().st_mtime
    try:
        last = float(EBIRJA_EXPORT_MARKER.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        last = 0.0
    if mtime <= last:
        log.info("ebirja-export: %s unchanged since the last import", path.name)
        return 0

    try:
        records, report, _match = load_ebirja_export(path)
    except ValueError as exc:
        # A required column is missing, so nothing is written and the marker is left alone: the
        # next cycle retries, and the message carries the file's own headers so the mapping in
        # ebirja_export_mapping.yaml can be corrected. Repeating it every cycle is the point --
        # the column wordings were never verified against a real export.
        log.error("ebirja-export: %s", exc)
        return 0
    except Exception as exc:
        log.error("ebirja-export: could not read %s: %s", path, exc)
        return 0

    for line in report.summary().splitlines():
        log.info("ebirja-export: %s", line.strip())

    inserted = 0
    if records:
        with session_scope() as session:
            stats = import_ebirja_export(session, records)
        log.info("ebirja-export import result: %s", stats)
        inserted = stats.get("inserted", 0)
    # Written after a successful read even when the file held nothing usable: it has given all
    # it will give until the owner replaces it.
    EBIRJA_EXPORT_MARKER.parent.mkdir(parents=True, exist_ok=True)
    EBIRJA_EXPORT_MARKER.write_text(str(mtime), encoding="utf-8")
    return inserted


COOP_MARKER = Path(__file__).resolve().parents[1] / "out" / ".cooperation_imported_mtime"


def sync_cooperation() -> int:
    """Import the weekly cooperation.uz plans JSON when it is newer than the last import.

    The scrape itself runs on the owner's Mac (cooperation.uz blocks foreign IPs); this step
    only reads the file it leaves behind. Disable with COOPERATION_IMPORT=0.
    """
    if os.environ.get("COOPERATION_IMPORT", "1").strip() == "0":
        log.info("cooperation: import disabled (COOPERATION_IMPORT=0)")
        return 0
    from radar.source.cooperation import import_cooperation, json_path, load_cooperation_json

    path = json_path()
    if not path.is_file():
        log.info("cooperation: %s not found; skipping", path)
        return 0
    mtime = path.stat().st_mtime
    try:
        last = float(COOP_MARKER.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        last = 0.0
    if mtime <= last:
        log.info("cooperation: no new plans file since the last import")
        return 0
    records = load_cooperation_json(path)
    with session_scope() as session:
        stats = import_cooperation(session, records)
    COOP_MARKER.parent.mkdir(parents=True, exist_ok=True)
    COOP_MARKER.write_text(str(mtime), encoding="utf-8")
    log.info("cooperation import result: %s (plans=%d)", stats, len(records))
    return int(stats.get("inserted", 0))


def sync_uzex(limit_per_module: int = 100) -> int:
    log.info("Starting UZEX synchronization across all modules...")
    client = UzexClient()
    records = []

    def each(label: str, fetch_list, build):
        """Per-record guard: one malformed deal must not discard the whole module."""
        try:
            deals = fetch_list()
        except Exception as exc:
            log.warning("UZEX %s list fetch failed: %s", label, exc)
            return
        for d in deals:
            try:
                records.append(build(d))
            except Exception as exc:
                log.warning("UZEX %s: skipping record %s: %s", label, d.get("id"), exc)

    # 1. Auction Deals + Contract Items
    each(
        "auction",
        lambda: client.fetch_auction_deals(from_idx=1, to_idx=limit_per_module),
        lambda d: parse_uzex_auction_deal(
            d, products=(client.fetch_auction_deal_products(d["lot_id"]) if d.get("lot_id") else [])
        ),
    )

    # 2. E-Tender & Otbor Deals + Budget Products
    each(
        "etender",
        lambda: client.fetch_etender_deals(from_idx=1, to_idx=limit_per_module, system_id=0),
        lambda d: parse_uzex_etender_deal(
            d,
            trade_info=client.fetch_etender_trade_detail(d["trade_id"])
            if d.get("trade_id")
            else None,
        ),
    )

    # 3. Direct Purchases + Detailed Items
    each(
        "direct",
        lambda: client.fetch_direct_purchases(from_idx=1, to_idx=limit_per_module),
        lambda d: parse_uzex_direct_purchase(
            d, detail=client.fetch_direct_purchase_detail(d["id"]) if d.get("id") else None
        ),
    )

    with session_scope() as session:
        stats = import_uzex_records(session, records)
        log.info("UZEX import result: %s", stats)
        return stats.get("inserted", 0)


def refresh_renewals() -> int:
    """Rebuild the Radar from the current classifications.

    Without this the Radar freezes at whenever someone last ran `radar renewal` by hand:
    every contract ingested afterwards is classified but never becomes an opportunity,
    so the one screen the sales team works from silently stops growing.
    """
    with session_scope() as session:
        count = compute_renewals(session)
    log.info("Renewal opportunities recomputed: %d", count)
    return count


# What "Connection closed" means here, confirmed against the host on 2026-11-16: the deploy key
# still authenticates, but the account's login shell is /sbin/nologin (a path that does not even
# exist on that server) and the sftp subsystem is closed too, so neither scp protocol can start
# a remote process. That is the shape of a Hostinger plan with SSH access switched off, and no
# change in this repository can work around it -- it is re-enabled in hPanel, under
# Advanced -> SSH Access.
_SHELLLESS_HINT = (
    " The key authenticates but the account has no usable shell and no sftp subsystem, which is "
    "how a Hostinger plan looks when SSH access is switched off. Re-enable it in hPanel "
    "(Advanced -> SSH Access); nothing in this repository can work around it."
)


def _deploy_error(proc: subprocess.CompletedProcess) -> str:
    """scp's own reason for failing, plus the remediation when we recognise the reason.

    OpenSSH 10 prints a three-line post-quantum advisory to stderr on every connection to an
    older server. It is not this failure and it is four times longer than the reason, so it is
    dropped rather than left to bury the one line a reader came for.
    """
    lines = [
        ln.strip()
        for ln in (proc.stderr or "").splitlines()
        if ln.strip() and not ln.lstrip().startswith("**")
    ]
    stderr = " ".join(lines) or f"scp exited {proc.returncode}"
    if "Connection closed" in stderr or "Permission denied" in stderr:
        return stderr + _SHELLLESS_HINT
    return stderr


def rebuild_and_deploy():
    log.info("Rebuilding dashboard and deploying to production...")
    with session_scope() as session:
        now = datetime.datetime.now(datetime.UTC)
        r_rows = radar_rows(session, now=now, limit=100)

        stats = {
            "total_procedures": session.query(Procedure).count(),
            "ebirja_count": session.query(Procedure).filter(Procedure.source == "ebirja").count(),
            "uzex_count": session.query(Procedure).filter(Procedure.source == "uzex").count(),
            "xt_count": session.query(Procedure).filter(Procedure.source == "xt_xarid").count(),
            "organizations": session.query(Organization).count(),
            "classified_it": session.query(Classification)
            .filter(Classification.is_it.is_(True))
            .count(),
            "radar_opportunities": len(r_rows),
        }

        radar_data = []
        for idx, r in enumerate(r_rows[:50], 1):
            ai_sample = generate_ai_recommendation(
                {
                    "title": r.title,
                    "amount": float(r.amount) if r.amount else 0,
                    "customer": {"name": r.customer, "stir": r.stir, "region": r.region},
                    "category": r.category or "IT",
                    "items": [{"raw_name": r.title, "brand": r.brand}],
                    "date": (
                        r.last_purchase_at.strftime("%Y-%m-%d")
                        if r.last_purchase_at
                        else "2026-03-01"
                    ),
                }
            )
            radar_data.append(
                {
                    "procedure_id": idx,
                    "customer": r.customer,
                    "score": r.score,
                    "contact_by": r.contact_by_at.strftime("%Y-%m-%d") if r.contact_by_at else "",
                    "category": r.category or "IT",
                    "brand": r.brand or "",
                    "amount": float(r.amount) if r.amount is not None else 0,
                    "expected_renewal": (
                        r.expected_renewal_at.strftime("%Y-%m-%d") if r.expected_renewal_at else ""
                    ),
                    "last_purchase": (
                        r.last_purchase_at.strftime("%Y-%m-%d") if r.last_purchase_at else ""
                    ),
                    "stir": r.stir or "",
                    "region": r.region or "",
                    "title": r.title,
                    "source_url": r.source_url or "",
                    "ai_advice": ai_sample,
                }
            )

        kw_sample = search_keywords(session, "Server", limit=20)
        cust_sample = search_customer_intelligence(session, "Bank", limit=10)
        comp_sample = search_competitor_intelligence(session, "Server", limit=10)

        # Every awarded contract, newest first. Sorting INN-complete rows to the top and
        # cutting at 1000 used to hide ~3.8k awarded contracts behind a page that looked
        # 100% complete; winner STIR is absent for most E-Birja rows because the public
        # list API does not carry it, and that gap has to stay visible.
        q_export = text("""
            SELECT
                COALESCE(c_org.name_canonical, '') AS customer_name,
                COALESCE(c_org.stir, '') AS customer_inn,
                COALESCE(li.names, p.title) AS product_name,
                TO_CHAR(COALESCE(p.published_at, p.completed_at), 'YYYY-MM-DD') AS contract_date,
                TO_CHAR(COALESCE(ro.expected_renewal_at, p.deadline_at,
                                 p.completed_at + interval '1 year'),
                        'YYYY-MM-DD') AS contract_end_date,
                COALESCE(p.start_price, 0) AS start_sum,
                COALESCE(aw.amount, p.start_price, 0) AS deal_sum,
                COALESCE(s_org.name_canonical, '') AS winner_name,
                COALESCE(s_org.stir, '') AS winner_inn,
                COALESCE(p.source_url, '') AS lot_url,
                p.source AS source
            FROM procedure p
            LEFT JOIN organization c_org ON c_org.id = p.customer_org_id
            -- Aggregated, not joined: a contract with three line items must stay one row,
            -- otherwise its amount is counted three times when the column is summed.
            LEFT JOIN LATERAL (
                SELECT string_agg(DISTINCT x.raw_name, '; ') AS names
                FROM lot_item x WHERE x.procedure_id = p.id
            ) li ON TRUE
            LEFT JOIN award aw ON aw.procedure_id = p.id
            LEFT JOIN organization s_org ON s_org.id = aw.supplier_org_id
            LEFT JOIN renewal_opportunity ro ON ro.procedure_id = p.id
            WHERE s_org.name_canonical IS NOT NULL AND s_org.name_canonical != ''
            ORDER BY COALESCE(p.completed_at, p.published_at) DESC NULLS LAST
            LIMIT :limit;
        """)
        export_rows = session.execute(q_export, {"limit": EXPORT_ROW_LIMIT}).fetchall()
        export_items = []
        for er in export_rows:
            d = dict(er._mapping)
            d["start_sum"] = float(d["start_sum"])
            d["deal_sum"] = float(d["deal_sum"])
            export_items.append(d)
        with_inn = sum(1 for d in export_items if d["winner_inn"])
        total_awarded = (
            session.execute(
                text("""
            SELECT COUNT(*) FROM procedure p
            JOIN award aw ON aw.procedure_id = p.id
            JOIN organization s ON s.id = aw.supplier_org_id
            WHERE COALESCE(TRIM(s.name_canonical), '') <> ''
        """)
            ).scalar()
            or 0
        )
        omitted = max(0, total_awarded - len(export_items))
        stats["export_rows"] = len(export_items)
        stats["export_rows_with_winner_inn"] = with_inn
        stats["export_rows_total"] = total_awarded
        stats["export_rows_omitted"] = omitted
        log.info(
            "Export: %d of %d awarded contracts, %d (%.0f%%) carry a winner STIR",
            len(export_items),
            total_awarded,
            with_inn,
            100 * with_inn / len(export_items) if export_items else 0,
        )
        if omitted:
            log.warning(
                "Dashboard shows the %d most recent awarded contracts; %d older "
                "ones do not fit the page. The Excel export carries all of them.",
                len(export_items),
                omitted,
            )

    settings = load_settings()
    if not settings.dashboard_data_path:
        log.info("DASHBOARD_DATA_PATH not set; skipping dashboard rebuild and deploy.")
        return

    json_path = Path(os.path.expanduser(settings.dashboard_data_path))
    data = {
        "stats": stats,
        "radar_data": radar_data,
        "kw_sample": kw_sample,
        "cust_sample": cust_sample,
        "comp_sample": comp_sample,
        "export_items": export_items,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    log.info("Wrote dashboard data (%d export rows) to %s", len(export_items), json_path)

    if settings.dashboard_build_script:
        compile_script = Path(os.path.expanduser(settings.dashboard_build_script))
        subprocess.run([sys.executable, str(compile_script)], check=True, timeout=300)
        log.info("Rebuilt dashboard via %s", compile_script)

    if not settings.deploy_configured:
        log.info("Deploy target not configured; dashboard built but not uploaded.")
        return

    scp_cmd = [
        "scp",
        "-o",
        "BatchMode=yes",
        "-P",
        settings.deploy_ssh_port,
        "-i",
        os.path.expanduser(settings.deploy_ssh_key),
        os.path.expanduser(settings.dashboard_html_path),
        settings.deploy_target,
    ]
    # check=True raised CalledProcessError without scp's own stderr, so the worker log said only
    # "exit status 1" and the reason sat in a separate stream. Capture it and report it.
    proc = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"Dashboard upload failed: {_deploy_error(proc)}")
    log.info("Successfully deployed the updated dashboard.")


def dispatch_alerts() -> dict[str, object]:
    """Dispatch automated Telegram alerts for unalerted HOT renewal opportunities."""
    from radar.alerts.telegram import send_hot_opportunity_alerts

    settings = load_settings()
    with session_scope() as session:
        stats = send_hot_opportunity_alerts(session, settings)
        session.commit()
    return stats


def _step(label: str, fn, default=None):
    """Run one cycle stage. A stage that fails is logged and the cycle continues."""
    try:
        return fn()
    except Exception:
        log.exception("Worker stage %r failed; continuing with the rest of the cycle.", label)
        return default


def run_once() -> dict[str, object]:
    """Run one full cycle. Never raises: a broken stage must not kill the daemon."""
    started = datetime.datetime.now(datetime.UTC)
    ins_eb = _step("sync_ebirja", sync_ebirja, default=0)
    ins_ebx = _step("sync_ebirja_export", sync_ebirja_export, default=0)
    ins_uz = _step("sync_uzex", sync_uzex, default=0)
    ins_coop = _step("sync_cooperation", sync_cooperation, default=0)
    renewals = _step("refresh_renewals", refresh_renewals, default=0)
    alerts = _step("dispatch_alerts", dispatch_alerts, default={"sent": 0})
    deployed = _step("rebuild_and_deploy", lambda: (rebuild_and_deploy(), True)[1], default=False)
    alerts_sent = alerts.get("sent", 0) if isinstance(alerts, dict) else 0
    result = {
        "started_at": started.isoformat(),
        "ebirja_inserted": ins_eb,
        "ebirja_export_inserted": ins_ebx,
        "uzex_inserted": ins_uz,
        "cooperation_inserted": ins_coop,
        "renewal_opportunities": renewals,
        "alerts_sent": alerts_sent,
        "deployed": deployed,
        "duration_s": round((datetime.datetime.now(datetime.UTC) - started).total_seconds(), 1),
    }
    log.info("Worker cycle finished: %s", result)
    return result


if __name__ == "__main__":
    run_once()
