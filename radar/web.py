"""FastAPI application: Secure Tender Radar dashboard, auth, export and APIs."""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import and_, or_, select, text

from radar.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session_token,
    get_current_user,
    get_current_user_optional,
    limiter,
    require_role,
    verify_password,
)
from radar.db import get_engine, session_scope
from radar.export import export_workbook
from radar.models import (
    Classification,
    ExportLog,
    Organization,
    Procedure,
    RenewalOpportunity,
    User,
)
from radar.renewal import load_lifecycle, radar_rows
from radar.security import SecurityHeadersMiddleware
from radar.stats import collect_stats

log = logging.getLogger("radar.web")

# Disable docs in production environment
is_prod = os.environ.get("APP_ENV") == "production"
app = FastAPI(
    title="Tender Radar",
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
    openapi_url=None if is_prod else "/openapi.json",
)

# AppSec middleware and rate limiting
app.add_middleware(SecurityHeadersMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.autoescape = True


# -----------------------------------------------------------------------------
# Health & Status
# -----------------------------------------------------------------------------
@app.get("/health")
def health() -> JSONResponse:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "database": type(exc).__name__},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return JSONResponse({"status": "ok", "database": "ok"})


# -----------------------------------------------------------------------------
# Authentication & Session Routes
# -----------------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/radar") -> Response:
    user = get_current_user_optional(request.cookies.get(SESSION_COOKIE_NAME))
    if user:
        return RedirectResponse(url=next or "/radar", status_code=status.HTTP_302_FOUND)

    return TEMPLATES.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
            "next_url": next,
            "csrf_token": os.urandom(16).hex(),
        },
    )


@app.post("/login", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "/radar",
    csrf_token: Annotated[str, Form()] = "",
) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    clean_username = username.strip()

    with session_scope() as session:
        user = session.scalar(select(User).where(User.username == clean_username))
        if not user or not user.is_active or not verify_password(user.password_hash, password):
            log.warning(
                "SECURITY: Failed login attempt for username=%r from IP=%s",
                clean_username,
                client_ip,
            )
            return TEMPLATES.TemplateResponse(
                request,
                "login.html",
                {
                    "error": "Noto'g'ri foydalanuvchi nomi yoki parol.",
                    "next_url": next,
                    "csrf_token": csrf_token or os.urandom(16).hex(),
                },
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        # Update last login timestamp
        user.last_login_at = datetime.now(UTC)
        session.commit()

        session_token = create_session_token(user.id, user.username, user.role)
        target_url = next if (next and next.startswith("/")) else "/radar"
        response = RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_token,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=is_prod or (request.url.scheme == "https"),
        )
        log.info(
            "User %r (role=%s) logged in successfully from IP=%s",
            user.username,
            user.role,
            client_ip,
        )
        return response


@app.get("/logout")
@app.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


# -----------------------------------------------------------------------------
# Protected Dashboard
# -----------------------------------------------------------------------------
@app.get("/radar", response_class=HTMLResponse)
def radar(
    request: Request,
    page: int = 1,
    per_page: int = 50,
    category: str | None = None,
    brand: str | None = None,
    min_amount: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Response:
    user = get_current_user_optional(request.cookies.get(SESSION_COOKIE_NAME))
    if not user:
        return RedirectResponse(url="/login?next=/radar", status_code=status.HTTP_302_FOUND)

    safe_page = max(1, page)
    safe_per_page = max(10, min(100, per_page))
    offset = (safe_page - 1) * safe_per_page

    dt_from = None
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from).replace(tzinfo=UTC)
        except ValueError:
            dt_from = None

    dt_to = None
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to).replace(tzinfo=UTC)
        except ValueError:
            dt_to = None

    now = datetime.now(UTC)
    config = load_lifecycle()
    with session_scope() as session:
        rows, total_count = radar_rows(
            session,
            now=now,
            limit=safe_per_page,
            offset=offset,
            category=category,
            brand=brand,
            min_amount=min_amount,
            date_from=dt_from,
            date_to=dt_to,
            return_total=True,
        )
        stats = collect_stats(session)
        sources = sorted(s for s in session.scalars(select(Procedure.source).distinct()) if s)

        # Top Buyers query (STIR not null)
        top_buyers = [
            dict(r)
            for r in session.execute(
                text("""
                SELECT o.id, o.name_canonical, o.stir, o.region,
                       COUNT(p.id) as proc_count,
                       COALESCE(SUM(COALESCE(a.amount, p.start_price, 0)), 0) as total_spent
                FROM organization o
                JOIN procedure p ON p.customer_org_id = o.id AND p.merged_from_id IS NULL
                LEFT JOIN award a ON a.procedure_id = p.id
                WHERE o.stir IS NOT NULL AND trim(o.stir) != ''
                GROUP BY o.id, o.name_canonical, o.stir, o.region
                ORDER BY total_spent DESC
                LIMIT 10;
            """)
            ).mappings().all()
        ]

        # Top Competitors query (STIR not null)
        top_competitors = [
            dict(r)
            for r in session.execute(
                text("""
                SELECT o.id, o.name_canonical, o.stir, o.region,
                       COUNT(a.procedure_id) AS wins_count,
                       COALESCE(SUM(a.amount), 0) AS total_amount,
                       COUNT(DISTINCT p.customer_org_id) AS unique_buyers,
                       AVG(CASE
                           WHEN p.start_price IS NOT NULL
                                AND p.start_price > 0
                                AND a.amount IS NOT NULL
                           THEN (p.start_price - a.amount) / p.start_price
                           ELSE 0
                       END) AS avg_discount
                FROM organization o
                JOIN award a ON a.supplier_org_id = o.id
                JOIN procedure p ON p.id = a.procedure_id AND p.merged_from_id IS NULL
                WHERE o.stir IS NOT NULL AND trim(o.stir) != ''
                GROUP BY o.id, o.name_canonical, o.stir, o.region
                HAVING COUNT(a.procedure_id) > 0
                ORDER BY total_amount DESC
                LIMIT 10;
            """)
            ).mappings().all()
        ]

        # Distinct categories for filter dropdown
        distinct_categories = [
            c
            for c in session.scalars(
                select(RenewalOpportunity.category)
                .distinct()
                .order_by(RenewalOpportunity.category)
            ).all()
            if c
        ]

    total_pages = max(1, (total_count + safe_per_page - 1) // safe_per_page)

    return TEMPLATES.TemplateResponse(
        request,
        "radar.html",
        {
            "rows": rows,
            "total_count": total_count,
            "current_page": safe_page,
            "total_pages": total_pages,
            "per_page": safe_per_page,
            "selected_category": category,
            "selected_brand": brand,
            "selected_min_amount": min_amount,
            "selected_date_from": date_from,
            "selected_date_to": date_to,
            "distinct_categories": distinct_categories,
            "top_buyers": top_buyers,
            "top_competitors": top_competitors,
            "stats": stats,
            "current_user": user,
            "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
            "synthetic_sources": [s for s in sources if s != "uzex"],
            "due_now": sum(1 for r in rows if r.contact_by_at and r.contact_by_at <= now),
            "max_score": config["scoring"]["max_reachable"],
            "window_days": config["radar_contact_window_days"],
        },
    )


# -----------------------------------------------------------------------------
# Admin Review UI & API (Admin Role Only)
# -----------------------------------------------------------------------------
@app.get("/admin/review", response_class=HTMLResponse)
def admin_review_page(request: Request) -> Response:
    user = get_current_user_optional(request.cookies.get(SESSION_COOKIE_NAME))
    if not user:
        return RedirectResponse(url="/login?next=/admin/review", status_code=status.HTTP_302_FOUND)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ushbu sahifaga kirish uchun admin huquqi talab qilinadi",
        )

    from radar.classify.rules import CATEGORIES

    with session_scope() as session:
        stmt = (
            select(Classification, Procedure, Organization)
            .join(Procedure, Procedure.id == Classification.procedure_id)
            .join(Organization, Organization.id == Procedure.customer_org_id, isouter=True)
            .where(
                or_(
                    Classification.needs_review.is_(True),
                    and_(
                        Classification.is_it.is_(True),
                        Classification.confidence < 0.7,
                    ),
                )
            )
            .order_by(Classification.confidence.asc().nullslast(), Procedure.id.desc())
            .limit(100)
        )
        items = []
        for clf, proc, cust in session.execute(stmt).all():
            items.append({
                "procedure_id": proc.id,
                "source": proc.source,
                "source_id": proc.source_id,
                "source_url": proc.source_url,
                "title": proc.title,
                "customer_name": cust.name_canonical if cust else "Noma'lum",
                "customer_stir": cust.stir if cust else None,
                "category": clf.category,
                "brand": clf.brand,
                "is_it": clf.is_it,
                "confidence": float(clf.confidence) if clf.confidence is not None else 0.5,
            })

    return TEMPLATES.TemplateResponse(
        request,
        "admin_review.html",
        {
            "items": items,
            "categories": sorted(CATEGORIES),
            "current_user": user,
        },
    )


@app.post("/api/admin/review/{procedure_id}")
async def api_admin_review_submit(
    procedure_id: int,
    request: Request,
    user: Annotated[User, Depends(require_role("admin"))],
) -> JSONResponse:
    from radar.models import Classification
    from radar.renewal import compute_renewals

    is_json = request.headers.get("content-type", "").startswith("application/json")
    payload = await request.json() if is_json else {}
    is_it = bool(payload.get("is_it", True))
    category = payload.get("category") if is_it else None
    brand = payload.get("brand") if is_it else None

    with session_scope() as session:
        clf = session.get(Classification, procedure_id)
        if not clf:
            return JSONResponse({"error": "Classification not found"}, status_code=404)

        clf.is_it = is_it
        clf.category = category
        if brand is not None:
            clf.brand = brand
        clf.method = "manual"
        clf.confidence = 1.0
        clf.needs_review = False
        session.commit()

        # Recompute renewals immediately without caching to AI
        compute_renewals(session)

    log.info(
        "ADMIN REVIEW: User %s updated procedure %d -> is_it=%s, category=%s",
        user.username,
        procedure_id,
        is_it,
        category,
    )
    return JSONResponse({
        "status": "ok",
        "procedure_id": procedure_id,
        "is_it": is_it,
        "category": category,
    })


# -----------------------------------------------------------------------------
# Protected Data Export API (Audit Logged & Injection Sanitized)
# -----------------------------------------------------------------------------
@app.get("/api/export/xlsx")
def api_export_xlsx(
    user: Annotated[User, Depends(get_current_user)],
    limit: int = 5000,
) -> Response:
    """Download verified radar Excel export with audit logging and max 5,000 rows cap."""
    safe_limit = min(max(1, limit), 5000)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    with session_scope() as session:
        _, row_count = export_workbook(session, path=tmp_path, limit=safe_limit)

        # Audit log entry
        audit_entry = ExportLog(
            user_id=user.id,
            export_type="xlsx",
            filter_json={"limit": safe_limit},
            row_count=row_count,
        )
        session.add(audit_entry)
        session.commit()

        log.info(
            "AUDIT: User %s (id=%d) exported %d rows to XLSX",
            user.username,
            user.id,
            row_count,
        )

    return FileResponse(
        path=tmp_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"renewal_radar_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}.xlsx",
    )


# -----------------------------------------------------------------------------
# Protected CRM & Intelligence APIs
# -----------------------------------------------------------------------------
@app.get("/api/companies/{stir}/timeline")
def api_company_timeline(
    stir: str,
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    from radar.crm import get_company_profile_and_timeline

    with session_scope() as session:
        data = get_company_profile_and_timeline(session, stir)
    status_code = 200 if data.get("found") else 404
    return JSONResponse(data, status_code=status_code)


@app.get("/api/companies/{stir}/proposal")
def api_company_proposal(
    stir: str,
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    from radar.crm import generate_grounded_proposal

    with session_scope() as session:
        data = generate_grounded_proposal(session, stir)
    status_code = 200 if "error" not in data else 404
    return JSONResponse(data, status_code=status_code)


@app.post("/api/procedures/{procedure_id}/bitrix")
async def api_procedure_bitrix(
    procedure_id: int,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
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
def api_search(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    q: str = "",
    type: str = "keyword",
    limit: int = 50,
) -> JSONResponse:
    from radar.search import (
        search_competitor_intelligence,
        search_customer_intelligence,
        search_keywords,
        search_products,
    )

    stir = request.query_params.get("stir")
    product = request.query_params.get("product")
    c_stir = request.query_params.get("customer_stir")
    s_stir = request.query_params.get("supplier_stir")

    with session_scope() as session:
        if type == "customer":
            data = search_customer_intelligence(session, q, stir=stir, limit=limit)
        elif type == "competitor":
            data = search_competitor_intelligence(session, q, stir=stir, limit=limit)
        elif type in ("product", "products"):
            prod_query = product or q
            data = search_products(session, prod_query, limit=limit)
        else:
            res = search_keywords(
                session,
                query=q,
                limit=limit,
                product_query=product,
                customer_stir=c_stir,
                supplier_stir=s_stir,
            )
            data = {"results": res, "query": q, "count": len(res)}
    return JSONResponse(data)


@app.get("/api/ai/recommendation")
def api_ai_recommendation(
    procedure_id: int,
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    from radar.ai_advisor import get_recommendation_for_procedure

    with session_scope() as session:
        data = get_recommendation_for_procedure(session, procedure_id)
    return JSONResponse(data)


@app.post("/api/ai/recommendation")
async def api_ai_recommendation_custom(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    from radar.ai_advisor import generate_ai_recommendation

    is_json = request.headers.get("content-type", "").startswith("application/json")
    payload = await request.json() if is_json else {}
    data = generate_ai_recommendation(payload)
    return JSONResponse(data)


@app.post("/api/ebirja/sync")
async def api_ebirja_sync(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    from radar.source.ebirja import (
        EbirjaClient,
        import_ebirja_records,
        parse_ebirja_contract,
    )

    is_json = request.headers.get("content-type", "").startswith("application/json")
    payload = await request.json() if is_json else {}
    search_term = payload.get("search")
    limit = int(payload.get("limit", 20))

    client = EbirjaClient()
    records = []

    shop_res = client.fetch_shop_contracts(
        page=0, per_page=min(limit, 50), search=search_term, shop_type="e-shop"
    )
    for item in shop_res.get("result", {}).get("data", []):
        records.append(parse_ebirja_contract(item, contract_type="Shop"))

    with session_scope() as session:
        stats = import_ebirja_records(session, records)

    return JSONResponse({
        "status": "ok",
        "fetched_count": len(records),
        "imported": stats,
    })


@app.get("/api/eimzo/status")
def api_eimzo_status(user: Annotated[User, Depends(get_current_user)]) -> JSONResponse:
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
def api_eimzo_challenge(user: Annotated[User, Depends(get_current_user)]) -> JSONResponse:
    from radar.eimzo import EImzoManager

    mgr = EImzoManager()
    res = mgr.get_challenge()
    return JSONResponse(res)


@app.post("/api/eimzo/verify")
async def api_eimzo_verify(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    from radar.config import load_settings
    from radar.eimzo import EImzoManager

    mgr = EImzoManager()
    is_json = request.headers.get("content-type", "").startswith("application/json")
    payload = await request.json() if is_json else {}

    pkcs7 = payload.get("pkcs7")
    token = payload.get("token")
    tin = payload.get("tin") or load_settings().company_tin

    if pkcs7:
        res = mgr.verify_and_login(pkcs7)
        return JSONResponse(res)
    elif token:
        saved = mgr.save_session(token=token, tin=tin)
        return JSONResponse({"status": "ok", "saved": saved})
    return JSONResponse({"status": "error", "message": "pkcs7 or token required"}, status_code=400)


@app.get("/")
def index() -> JSONResponse:
    return JSONResponse({"endpoints": ["/radar", "/health"]})


