"""FastAPI application: GET /radar (HTML) and GET /health (JSON)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text

from radar.db import get_engine, session_scope
from radar.models import Procedure
from radar.renewal import load_lifecycle, radar_rows
from radar.stats import collect_stats

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="Tender Radar", docs_url=None, redoc_url=None)


@app.get("/health")
def health() -> JSONResponse:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse({"status": "error", "database": type(exc).__name__},
                            status_code=503)
    return JSONResponse({"status": "ok", "database": "ok"})


@app.get("/radar", response_class=HTMLResponse)
def radar(request: Request, limit: int = 200) -> HTMLResponse:
    now = datetime.now(UTC)
    config = load_lifecycle()
    with session_scope() as session:
        rows = radar_rows(session, now=now, limit=limit)
        stats = collect_stats(session)
        sources = sorted(s for s in session.scalars(select(Procedure.source).distinct()) if s)
    return TEMPLATES.TemplateResponse(request, "radar.html", {
        "rows": rows,
        "stats": stats,
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "synthetic_sources": [s for s in sources if s != "uzex"],
        "due_now": sum(1 for r in rows if r.contact_by_at and r.contact_by_at <= now),
        "max_score": config["scoring"]["max_reachable"],
        "window_days": config["radar_contact_window_days"],
    })


@app.get("/api/companies/{stir}/timeline")
def api_company_timeline(stir: str) -> JSONResponse:
    from radar.crm import get_company_profile_and_timeline

    with session_scope() as session:
        data = get_company_profile_and_timeline(session, stir)
    status_code = 200 if data.get("found") else 404
    return JSONResponse(data, status_code=status_code)


@app.get("/api/companies/{stir}/proposal")
def api_company_proposal(stir: str) -> JSONResponse:
    from radar.crm import generate_grounded_proposal

    with session_scope() as session:
        data = generate_grounded_proposal(session, stir)
    status_code = 200 if "error" not in data else 404
    return JSONResponse(data, status_code=status_code)


@app.post("/api/procedures/{procedure_id}/bitrix")
async def api_procedure_bitrix(procedure_id: int, request: Request) -> JSONResponse:
    from radar.crm import push_deal_for_procedure

    payload: dict = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()

    with session_scope() as session:
        try:
            res = push_deal_for_procedure(
                session=session,
                procedure_id=procedure_id,
                title=payload.get("title"),
                amount=payload.get("amount"),
                use_mock=payload.get("mock", False),
            )
        except ValueError as exc:
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=404)
        except Exception as exc:
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=502)
    return JSONResponse(res)


@app.get("/api/search")
def api_search(q: str = "", type: str = "keyword", limit: int = 50) -> JSONResponse:
    from radar.search import (
        search_competitor_intelligence,
        search_customer_intelligence,
        search_keywords,
    )

    with session_scope() as session:
        if type == "customer":
            data = search_customer_intelligence(session, q, limit=limit)
        elif type == "competitor":
            data = search_competitor_intelligence(session, q, limit=limit)
        else:
            data = {"results": search_keywords(session, q, limit=limit), "query": q}
    return JSONResponse(data)


@app.get("/api/eimzo/status")
def api_eimzo_status() -> JSONResponse:
    from radar.eimzo import EImzoManager

    mgr = EImzoManager()
    daemon_info = mgr.check_daemon()
    session_info = mgr.get_session()
    return JSONResponse({
        "daemon": daemon_info,
        "session": {
            "authenticated": session_info.get("authenticated", False),
            "tin": session_info.get("tin"),
            "has_token": bool(session_info.get("token")),
            "last_updated": session_info.get("last_updated"),
        },
    })


@app.post("/api/eimzo/challenge")
def api_eimzo_challenge() -> JSONResponse:
    from radar.eimzo import EImzoManager

    mgr = EImzoManager()
    res = mgr.get_challenge()
    return JSONResponse(res)


@app.post("/api/eimzo/verify")
async def api_eimzo_verify(request: Request) -> JSONResponse:
    from radar.eimzo import EImzoManager

    mgr = EImzoManager()
    is_json = request.headers.get("content-type", "").startswith("application/json")
    payload = await request.json() if is_json else {}

    pkcs7 = payload.get("pkcs7")
    token = payload.get("token")
    tin = payload.get("tin", "308904387")

    if pkcs7:
        res = mgr.verify_and_login(pkcs7)
        return JSONResponse(res)
    elif token:
        saved = mgr.save_session(token=token, tin=tin)
        return JSONResponse({"status": "ok", "saved": saved})
    return JSONResponse({"status": "error", "message": "pkcs7 or token required"}, status_code=400)


@app.post("/api/ebirja/sync")
async def api_ebirja_sync(request: Request) -> JSONResponse:
    from radar.source.ebirja import (
        EbirjaClient,
        import_ebirja_records,
        parse_ebirja_auction,
        parse_ebirja_contract,
    )

    is_json = request.headers.get("content-type", "").startswith("application/json")
    payload = await request.json() if is_json else {}
    search_term = payload.get("search")
    limit = int(payload.get("limit", 20))

    client = EbirjaClient()
    records = []

    # 1. Shop contracts
    shop_res = client.fetch_shop_contracts(
        page=0, per_page=min(limit, 50), search=search_term, shop_type="e-shop"
    )
    for item in shop_res.get("result", {}).get("data", []):
        records.append(parse_ebirja_contract(item, contract_type="Shop"))

    # 2. National shop contracts
    nat_res = client.fetch_shop_contracts(
        page=0, per_page=min(limit, 20), search=search_term, shop_type="national-shop"
    )
    for item in nat_res.get("result", {}).get("data", []):
        records.append(parse_ebirja_contract(item, contract_type="National-Shop"))

    # 3. Tender contracts
    tender_res = client.fetch_tender_contracts(
        page=0, per_page=min(limit, 20), search=search_term, tender_type=1
    )
    for item in tender_res.get("result", {}).get("data", []):
        records.append(parse_ebirja_contract(item, contract_type="Tender"))

    # 4. Selection contracts
    sel_res = client.fetch_tender_contracts(
        page=0, per_page=min(limit, 20), search=search_term, tender_type=2
    )
    for item in sel_res.get("result", {}).get("data", []):
        records.append(parse_ebirja_contract(item, contract_type="Tanlov"))

    # 5. Offer requests
    offer_res = client.fetch_offer_requests(page=0, per_page=min(limit, 20), search=search_term)
    for item in offer_res.get("result", {}).get("data", []):
        records.append(parse_ebirja_contract(item, contract_type="Taklif"))

    # 6. Active auctions
    auc_res = client.fetch_active_auctions(page=1, size=min(limit, 20), search=search_term)
    for item in auc_res.get("result", {}).get("data", []):
        records.append(parse_ebirja_auction(item))

    with session_scope() as session:
        stats = import_ebirja_records(session, records)

    return JSONResponse({
        "status": "ok",
        "fetched_count": len(records),
        "imported": stats,
    })


@app.get("/")
def index() -> JSONResponse:
    return JSONResponse({"endpoints": ["/radar", "/health"]})

