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

from radar.db import session_scope
from radar.models import Procedure, Organization, Classification
from radar.renewal import radar_rows
from radar.search import search_keywords, search_customer_intelligence, search_competitor_intelligence
from radar.ai_advisor import generate_ai_recommendation
from radar.source.ebirja import (
    EbirjaClient,
    parse_ebirja_contract,
    parse_ebirja_auction,
    import_ebirja_records,
)

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "logs" / "worker.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("radar.worker")

def sync_ebirja() -> int:
    log.info("Starting E-Birja synchronization...")
    client = EbirjaClient()
    records = []

    # 1. Recent E-Shop (pages 0..2)
    for p in range(3):
        res = client.fetch_shop_contracts(page=p, per_page=50, shop_type="e-shop")
        items = res.get("result", {}).get("data", [])
        for it in items:
            records.append(parse_ebirja_contract(it, contract_type="Shop"))

    # 2. Recent National-Shop (pages 0..1)
    for p in range(2):
        res = client.fetch_shop_contracts(page=p, per_page=50, shop_type="national-shop")
        items = res.get("result", {}).get("data", [])
        for it in items:
            records.append(parse_ebirja_contract(it, contract_type="National-Shop"))

    # 3. Recent Tanlov & Taklif
    res_t2 = client.fetch_tender_contracts(page=0, per_page=30, tender_type=2)
    for it in res_t2.get("result", {}).get("data", []):
        records.append(parse_ebirja_contract(it, contract_type="Tanlov"))

    res_off = client.fetch_offer_requests(page=0, per_page=30)
    for it in res_off.get("result", {}).get("data", []):
        records.append(parse_ebirja_contract(it, contract_type="Taklif"))

    with session_scope() as session:
        stats = import_ebirja_records(session, records)
        log.info("E-Birja import result: %s", stats)
        return stats.get("inserted", 0)

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
            "classified_it": session.query(Classification).filter(Classification.is_it == True).count(),
            "radar_opportunities": len(r_rows),
        }

        radar_data = []
        for idx, r in enumerate(r_rows[:50], 1):
            ai_sample = generate_ai_recommendation({
                "title": r.title,
                "amount": float(r.amount) if r.amount else 0,
                "customer": {"name": r.customer, "stir": r.stir, "region": r.region},
                "category": r.category or "IT",
                "items": [{"raw_name": r.title, "brand": r.brand}],
                "date": r.last_purchase_at.strftime("%Y-%m-%d") if r.last_purchase_at else "2026-03-01",
            })
            radar_data.append({
                "procedure_id": idx,
                "customer": r.customer,
                "score": r.score,
                "contact_by": r.contact_by_at.strftime("%Y-%m-%d") if r.contact_by_at else "",
                "category": r.category or "IT",
                "brand": r.brand or "",
                "amount": float(r.amount) if r.amount is not None else 0,
                "expected_renewal": r.expected_renewal_at.strftime("%Y-%m-%d") if r.expected_renewal_at else "",
                "last_purchase": r.last_purchase_at.strftime("%Y-%m-%d") if r.last_purchase_at else "",
                "stir": r.stir or "",
                "region": r.region or "",
                "title": r.title,
                "source_url": r.source_url or "",
                "ai_advice": ai_sample,
            })

        kw_sample = search_keywords(session, "Server", limit=20)
        cust_sample = search_customer_intelligence(session, "Bank", limit=10)
        comp_sample = search_competitor_intelligence(session, "Server", limit=10)

    json_path = Path("/Users/admin/.gemini/antigravity/brain/c760dc22-7275-42ce-8fd5-982645b9cddb/scratch/updated_dashboard_data.json")
    data = {
        "stats": stats,
        "radar_data": radar_data,
        "kw_sample": kw_sample,
        "cust_sample": cust_sample,
        "comp_sample": comp_sample,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    compile_script = Path("/Users/admin/.gemini/antigravity/brain/c760dc22-7275-42ce-8fd5-982645b9cddb/scratch/build_clean_dashboard.py")
    subprocess.run([sys.executable, str(compile_script)], check=True)

    scp_cmd = [
        "scp", "-P", "65002", "-i", os.path.expanduser("~/.ssh/id_hostinger"),
        "/Users/admin/.gemini/antigravity/brain/c760dc22-7275-42ce-8fd5-982645b9cddb/mvp_dashboard.html",
        "u475605112@62.72.50.47:/home/u475605112/domains/softy.uz/public_html/radar/index.html",
    ]
    subprocess.run(scp_cmd, check=True)
    log.info("Successfully deployed updated dashboard to tender.softy.uz!")

def run_once():
    inserted = sync_ebirja()
    rebuild_and_deploy()
    log.info("Worker run completed. Inserted %d new contracts.", inserted)

if __name__ == "__main__":
    run_once()
