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


@app.get("/")
def index() -> JSONResponse:
    return JSONResponse({"endpoints": ["/radar", "/health"]})
