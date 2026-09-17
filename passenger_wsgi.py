"""
Softy Platforma — Hostinger Passenger WSGI Entry Point (tender.softy.uz)
Xavfsizlik: Gmail OTP 2FA (umrbaxt93@gmail.com), Bitrix24 Integration, Role-based filtering.
"""

import sys
import os
from pathlib import Path
import urllib.parse
import json

CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from app.server import (
    execute_search, get_company_profile_and_timeline,
    generate_grounded_proposal, assign_staff, create_sales_task, STAFF_MEMBERS
)
from app.export_service import export_data
from app.eimzo_auth import EImzoAuthManager
from app.sync_service import sync_manager
from app.database import db_session
from app.auth import (
    authenticate_user, validate_token, logout_user,
    change_password, get_admin_stats, get_all_tasks,
    update_task_status, create_member_user, get_all_users,
    create_session_for_user, IT_KEYWORDS
)
from app.email_service import (
    init_approval_table, create_email_otp, verify_email_otp, send_login_alert, OTP_EMAIL
)
from app.bitrix_service import create_radar_task, send_multiple_radar_tasks, get_all_sent_task_keys
from app.date_utils import calculate_accurate_end_date
from app.competitor_service import search_competitors, get_competitor_deep_intel

# CORS headers
# Faqat o'z domenimiz. '*' bo'lganda istalgan sayt brauzer orqali
# butun tender bazasini o'qiy olardi.
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://tender.softy.uz")

CORS_HEADERS = [
    ('Access-Control-Allow-Origin', ALLOWED_ORIGIN),
    ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
    ('Access-Control-Allow-Headers', 'Content-Type, Authorization, user-key'),
    ('Vary', 'Origin')
]


def json_resp(data, status="200 OK", extra_headers=None):
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    headers = list(CORS_HEADERS) + [("Content-Type", "application/json; charset=utf-8")]
    if extra_headers:
        headers.extend(extra_headers)
    return status, headers, body


def extract_token(environ, query_params):
    # LiteSpeed/Apache ba'zan sarlavhani REDIRECT_ prefiksi bilan uzatadi.
    auth = (environ.get("HTTP_AUTHORIZATION")
            or environ.get("REDIRECT_HTTP_AUTHORIZATION", ""))
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    if "token" in query_params:
        return query_params["token"][0]
    cookie = environ.get("HTTP_COOKIE", "")
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("softy_auth_token=") or part.startswith("softy_token="):
            return part.split("=", 1)[1].strip()
    return None


def is_it_lot(row: dict) -> bool:
    """IT yo'nalishiga tegishli lot ekanligini tekshirish."""
    text = f"{row.get('title') or ''} {row.get('category') or ''}".lower()
    return any(kw in text for kw in IT_KEYWORDS)


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    query_string = environ.get("QUERY_STRING", "")
    query_params = urllib.parse.parse_qs(query_string)

    if method == "OPTIONS":
        start_response("200 OK", list(CORS_HEADERS))
        return [b""]

    # ── Static file routing ──────────────────────────────────────────────────
    # Secret portal: /umid, /umid/, /radar, /radar/
    if path in ("/umid", "/umid/", "/umid/index.html"):
        umid_idx = CURRENT_DIR / "umid" / "index.html"
        if not umid_idx.exists():
            umid_idx = CURRENT_DIR / "index.html"
        if umid_idx.exists():
            content = umid_idx.read_bytes()
            start_response("200 OK", list(CORS_HEADERS) + [("Content-Type", "text/html; charset=utf-8")])
            return [content]

    if path in ("/radar", "/radar/", "/radar/index.html"):
        radar_idx = CURRENT_DIR / "radar" / "index.html"
        if not radar_idx.exists():
            radar_idx = CURRENT_DIR / "umid" / "index.html"
        if radar_idx.exists():
            content = radar_idx.read_bytes()
            start_response("200 OK", list(CORS_HEADERS) + [("Content-Type", "text/html; charset=utf-8")])
            return [content]

    # Root / and /index.html (404 niqob sahifasi)
    if path in ("/", "/index.html"):
        idx = CURRENT_DIR / "index.html"
        if idx.exists():
            content = idx.read_bytes()
            start_response("200 OK", list(CORS_HEADERS) + [("Content-Type", "text/html; charset=utf-8")])
            return [content]

    # ── Health check (public) ────────────────────────────────────────────────
    if path == "/api/health":
        st, hd, bd = json_resp({
            "status": "healthy", "app": "Softy Platforma",
            "domain": "tender.softy.uz", "hosting": "Hostinger",
            "baseline_start_date": "2024-01-01"
        })
        start_response(st, hd); return [bd]

    # Read POST body
    body = {}
    if method == "POST":
        try:
            clen = int(environ.get("CONTENT_LENGTH", 0))
            if clen > 0:
                raw = environ["wsgi.input"].read(clen)
                body = json.loads(raw.decode("utf-8"))
        except Exception:
            pass

    token = extract_token(environ, query_params)

    # ════════════════════════════════════════════════════════════════════════
    # AUTH ENDPOINTS (public)
    # ════════════════════════════════════════════════════════════════════════

    # POST /api/auth/login  → Login va parol orqali to'g'ridan-to'g'ri xavfsiz kirish
    if path == "/api/auth/login" and method == "POST":
        uname = (body.get("username") or "").strip()
        passwd = body.get("password", "")
        user = authenticate_user(uname, passwd)
        if not user:
            st, hd, bd = json_resp(
                {"success": False, "error": "Login yoki parol noto'g'ri kiritildi."},
                "401 Unauthorized"
            )
            start_response(st, hd); return [bd]

        # Muvaffaqiyatli autentifikatsiya -> Sessiya yaratish va token berish
        session = create_session_for_user(uname)
        if not session:
            st, hd, bd = json_resp(
                {"success": False, "error": "Foydalanuvchi topilmadi"},
                "401 Unauthorized"
            )
            start_response(st, hd); return [bd]

        # Xavfsizlik: fonda bildirishnoma yuborish (kirishni kechiktirmaydi)
        try:
            client_ip = environ.get("HTTP_X_FORWARDED_FOR") or environ.get("REMOTE_ADDR") or ""
            send_login_alert(uname, client_ip)
        except Exception:
            pass

        st, hd, bd = json_resp({
            "success": True,
            "token": session["token"],
            "user": session["user"],
            "expires_at": session["expires_at"],
            "message": f"Xush kelibsiz, {session['user'].get('full_name', uname)}!"
        })
        start_response(st, hd); return [bd]

    # POST /api/auth/verify-otp  → Step 2: OTP tekshirish va token berish
    if path == "/api/auth/verify-otp" and method == "POST":
        uname = (body.get("username") or "").strip()
        code = (body.get("code") or "").strip()
        if not uname or not code:
            st, hd, bd = json_resp(
                {"success": False, "error": "Foydalanuvchi nomi va kod talab qilinadi"},
                "400 Bad Request"
            )
            start_response(st, hd); return [bd]

        if not verify_email_otp(uname, code):
            st, hd, bd = json_resp(
                {"success": False, "error": "Tasdiqlash kodi noto'g'ri yoki muddati tugagan (5 daqiqa)."},
                "401 Unauthorized"
            )
            start_response(st, hd); return [bd]

        session = create_session_for_user(uname)
        if not session:
            st, hd, bd = json_resp(
                {"success": False, "error": "Foydalanuvchi topilmadi"},
                "401 Unauthorized"
            )
            start_response(st, hd); return [bd]

        st, hd, bd = json_resp({
            "success": True,
            "token": session["token"],
            "user": session["user"],
            "expires_at": session["expires_at"]
        })
        start_response(st, hd); return [bd]

    # POST /api/auth/logout
    if path == "/api/auth/logout" and method == "POST":
        t = token or body.get("token")
        if t:
            logout_user(t)
        st, hd, bd = json_resp({"success": True, "message": "Tizimdan chiqildi"})
        start_response(st, hd); return [bd]

    # GET /api/auth/me
    if path == "/api/auth/me" and method == "GET":
        user = validate_token(token) if token else None
        st, hd, bd = json_resp({"authenticated": bool(user), "user": user})
        start_response(st, hd); return [bd]

    # ════════════════════════════════════════════════════════════════════════
    # AVTORIZATSIYA TO'SIQ — bu yerdan pastdagi HAMMA endpoint token talab qiladi.
    # Yuqoridagilar ataylab ochiq: statik sahifalar, /api/health va /api/auth/*.
    # ════════════════════════════════════════════════════════════════════════
    current_user = validate_token(token) if token else None
    if not current_user:
        st, hd, bd = json_resp(
            {"success": False, "error": "Avtorizatsiya talab qilinadi. Iltimos, qaytadan kiring."},
            "401 Unauthorized"
        )
        start_response(st, hd); return [bd]

    # ════════════════════════════════════════════════════════════════════════
    # DATA & FUNCTIONAL ENDPOINTS (himoyalangan)
    # ════════════════════════════════════════════════════════════════════════

    # ── Sources ──────────────────────────────────────────────────────────────
    if path == "/api/sources":
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sources ORDER BY id ASC;")
            rows = [dict(r) for r in cursor.fetchall()]
        st, hd, bd = json_resp({"sources": rows})
        start_response(st, hd); return [bd]

    # ── Search (101k Lots) ───────────────────────────────────────────────────
    if path == "/api/search" and method == "POST":
        q_str = body.get("query_str") or body.get("query") or body.get("keyword") or ""
        body["query"] = q_str
        res = execute_search(body)
        st, hd, bd = json_resp(res)
        start_response(st, hd); return [bd]

    # ── Competitor Search across all exchange tenders (IT & Umumiy) ──────────
    if path == "/api/competitors/search":
        q = (
            query_params.get("query", [""])[0] or
            query_params.get("q", [""])[0] or
            (body.get("query") if isinstance(body, dict) else "") or ""
        )
        mode = (
            query_params.get("mode", ["it"])[0] or
            (body.get("mode") if isinstance(body, dict) else "it") or "it"
        )
        limit = int(
            query_params.get("limit", [50])[0] or
            (body.get("limit") if isinstance(body, dict) else 50) or 50
        )
        page = int(
            query_params.get("page", [1])[0] or
            (body.get("page") if isinstance(body, dict) else 1) or 1
        )
        res = search_competitors(query=q, mode=mode, limit=limit, page=page)
        st, hd, bd = json_resp(res)
        start_response(st, hd); return [bd]

    # ── Competitor Deep Intel: O'ynalgan Tashkilotlar & Barcha Lotlar ─────────
    if (path.startswith("/api/companies/") or path.startswith("/api/competitors/")) and path.endswith("/lots") and method == "GET":
        inn = path.strip("/").split("/")[2]
        res = get_competitor_deep_intel(inn)
        st, hd, bd = json_resp(res)
        start_response(st, hd); return [bd]

    # ── Bitrix24: Yagona lot topshiriq ──────────────────────────────────────
    if path == "/api/radar/send-one-to-bitrix" and method == "POST":
        try:
            lot = body.get("lot", body)
            advice = body.get("advice", "")
            result = create_radar_task(lot, advice)
            st, hd, bd = json_resp(result)
        except Exception as e:
            st, hd, bd = json_resp({"success": False, "error": str(e)})
        start_response(st, hd); return [bd]

    # ── Bitrix24: Ko'plab lot topshiriq ─────────────────────────────────────
    if path == "/api/radar/send-to-bitrix" and method == "POST":
        try:
            lots = body.get("lots", [])
            if not lots and body.get("lot"):
                lots = [body.get("lot")]
            if not lots:
                st, hd, bd = json_resp({"success": False, "error": "lots ro'yxati bo'sh"})
                start_response(st, hd); return [bd]
            result = send_multiple_radar_tasks(lots)
            st, hd, bd = json_resp(result)
        except Exception as e:
            st, hd, bd = json_resp({"success": False, "error": str(e)})
        start_response(st, hd); return [bd]

    # ── Bitrix24: Yuborilgan topshiriqlar kalitlari ro'yxati ─────────────────
    if path == "/api/radar/sent-tasks" and method == "GET":
        keys = get_all_sent_task_keys()
        st, hd, bd = json_resp({"sent_keys": keys})
        start_response(st, hd); return [bd]

    # ── Export (Excel & PDF) ─────────────────────────────────────────────────
    if path == "/api/export" and method == "GET":
        filters = {k: (v[0] if len(v) == 1 else v) for k, v in query_params.items()}
        if "platforms" in filters and isinstance(filters["platforms"], str):
            filters["platforms"] = [p.strip() for p in filters["platforms"].split(",") if p.strip()]
        fmt = filters.get("format", "xlsx").lower()
        content_data, media_type, filename = export_data(filters, format_type=fmt)
        resp_bytes = content_data.encode("utf-8") if isinstance(content_data, str) else content_data
        start_response("200 OK", list(CORS_HEADERS) + [
            ("Content-Type", media_type),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
            ("Content-Length", str(len(resp_bytes)))
        ])
        return [resp_bytes]

    # ── Company Profile & Proposal ───────────────────────────────────────────
    if path.startswith("/api/companies/") and path.endswith("/proposal"):
        inn = path.strip("/").split("/")[2]
        st, hd, bd = json_resp(generate_grounded_proposal(inn))
        start_response(st, hd); return [bd]

    if path.startswith("/api/companies/") and path.endswith("/assign") and method == "POST":
        inn = path.strip("/").split("/")[2]
        st, hd, bd = json_resp(assign_staff(inn, body.get("staff_id")))
        start_response(st, hd); return [bd]

    if path.startswith("/api/companies/") and path.endswith("/task") and method == "POST":
        inn = path.strip("/").split("/")[2]
        st, hd, bd = json_resp(create_sales_task(
            inn=inn,
            task_title=body.get("task_title", "Mijoz bilan aloqa"),
            task_type=body.get("task_type", "TAKTAK_TAYYORLASH"),
            assigned_staff_id=body.get("assigned_staff_id"),
            lot_id=body.get("lot_id"),
            proposal_summary=body.get("proposal_summary")
        ))
        start_response(st, hd); return [bd]

    if path.startswith("/api/companies/") and method == "GET":
        inn = path.strip("/").split("/")[-1]
        st, hd, bd = json_resp(get_company_profile_and_timeline(inn))
        start_response(st, hd); return [bd]

    # ── Staff ────────────────────────────────────────────────────────────────
    if path == "/api/staff":
        st, hd, bd = json_resp({"staff": STAFF_MEMBERS})
        start_response(st, hd); return [bd]

    # ── Gemini AI ────────────────────────────────────────────────────────────
    if path == "/api/gemini/analyze" and method == "POST":
        from app.gemini_service import analyze_lot_with_gemini
        lot_id = str(body.get("lot_id") or body.get("id") or body.get("lot_number") or "")
        st, hd, bd = json_resp(analyze_lot_with_gemini(lot_id))
        start_response(st, hd); return [bd]

    if path == "/api/gemini/key" and method == "POST":
        from app.gemini_service import set_gemini_api_key
        key = body.get("api_key", "")
        ok = set_gemini_api_key(key)
        st, hd, bd = json_resp({"success": ok})
        start_response(st, hd); return [bd]

    if path == "/api/gemini/status" and method == "GET":
        from app.gemini_service import get_gemini_api_key
        has_key = bool(get_gemini_api_key())
        st, hd, bd = json_resp({"has_key": has_key, "model": "gemini-1.5-flash"})
        start_response(st, hd); return [bd]

    # ── Admin Stats ──────────────────────────────────────────────────────────
    if path == "/api/admin/stats" and method == "GET":
        stats = get_admin_stats()
        st, hd, bd = json_resp({"stats": stats})
        start_response(st, hd); return [bd]

    # ── E-IMZO ───────────────────────────────────────────────────────────────
    if path == "/api/eimzo/status":
        daemon_info = EImzoAuthManager.check_daemon()
        sess_info = EImzoAuthManager.get_session()
        st, hd, bd = json_resp({"daemon": daemon_info, "session": sess_info})
        start_response(st, hd); return [bd]

    # 404
    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"404 Not Found"]
