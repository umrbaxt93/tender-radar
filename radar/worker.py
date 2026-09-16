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
    parse_ebirja_contract,
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


def _collect(records: list, label: str, fetch, parse) -> None:
    """Fetch one E-Birja page and parse it. A failure here skips the page, never the run."""
    try:
        items = fetch().get("result", {}).get("data", [])
    except Exception as exc:
        log.warning("E-Birja %s fetch failed: %s", label, exc)
        return
    for it in items:
        try:
            records.append(parse(it))
        except Exception as exc:
            log.warning("E-Birja %s: skipping malformed record: %s", label, exc)


def sync_ebirja() -> int:
    log.info("Starting E-Birja synchronization...")
    client = EbirjaClient()
    records: list = []

    # 1. Recent E-Shop (pages 0..2)
    for p in range(3):
        _collect(
            records,
            f"e-shop p{p}",
            lambda p=p: client.fetch_shop_contracts(page=p, per_page=50, shop_type="e-shop"),
            lambda it: parse_ebirja_contract(it, contract_type="Shop"),
        )

    # 2. Recent National-Shop (pages 0..1)
    for p in range(2):
        _collect(
            records,
            f"national-shop p{p}",
            lambda p=p: client.fetch_shop_contracts(page=p, per_page=50, shop_type="national-shop"),
            lambda it: parse_ebirja_contract(it, contract_type="National-Shop"),
        )

    # 3. Recent Tanlov & Taklif
    _collect(
        records,
        "tanlov",
        lambda: client.fetch_tender_contracts(page=0, per_page=30, tender_type=2),
        lambda it: parse_ebirja_contract(it, contract_type="Tanlov"),
    )
    _collect(
        records,
        "taklif",
        lambda: client.fetch_offer_requests(page=0, per_page=30),
        lambda it: parse_ebirja_contract(it, contract_type="Taklif"),
    )

    if not records:
        log.warning("E-Birja returned no usable records this cycle.")
        return 0

    with session_scope() as session:
        stats = import_ebirja_records(session, records)
        log.info("E-Birja import result: %s", stats)
        return stats.get("inserted", 0)


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
        "-P",
        settings.deploy_ssh_port,
        "-i",
        os.path.expanduser(settings.deploy_ssh_key),
        os.path.expanduser(settings.dashboard_html_path),
        settings.deploy_target,
    ]
    subprocess.run(scp_cmd, check=True, timeout=300)
    log.info("Successfully deployed updated dashboard to tender.softy.uz!")


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
    ins_uz = _step("sync_uzex", sync_uzex, default=0)
    renewals = _step("refresh_renewals", refresh_renewals, default=0)
    alerts = _step("dispatch_alerts", dispatch_alerts, default={"sent": 0})
    deployed = _step("rebuild_and_deploy", lambda: (rebuild_and_deploy(), True)[1], default=False)
    alerts_sent = alerts.get("sent", 0) if isinstance(alerts, dict) else 0
    result = {
        "started_at": started.isoformat(),
        "ebirja_inserted": ins_eb,
        "uzex_inserted": ins_uz,
        "renewal_opportunities": renewals,
        "alerts_sent": alerts_sent,
        "deployed": deployed,
        "duration_s": round((datetime.datetime.now(datetime.UTC) - started).total_seconds(), 1),
    }
    log.info("Worker cycle finished: %s", result)
    return result


if __name__ == "__main__":
    run_once()
