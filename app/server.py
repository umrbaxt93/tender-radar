"""
Softy Platforma — Web & REST API Server (Section 17)
Tarixiy xaridlar qidiruvi, ko'p o'lchamli filtrlar, korxonalar va shartnomalar,
CRM integratsiyasi (xodim biriktirish, vazifa, asoslangan taklif, Bitrix24),
ma'lumot manbalari monitoringi va eksport xizmati.
"""

import os
import json
import mimetypes
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.config import HOST, PORT, BASE_DIR, PLATFORMS, STAFF_MEMBERS, DOMAIN
from app.database import db_session, init_db
from app.filter_engine import execute_search
from app.crm_service import (
    get_company_profile_and_timeline,
    assign_staff,
    create_sales_task,
    generate_grounded_proposal,
    push_to_bitrix24
)
from app.export_service import export_data
from app.adapters.registry import get_adapter
from app.sync_service import sync_manager

FRONTEND_DIR = BASE_DIR / "frontend"

class SoftyRequestHandler(BaseHTTPRequestHandler):
    """
    Softy Platforma REST API va Frontend statik fayllar handler-i
    """

    def _send_json(self, data: Any, status_code: int = 200):
        response_bytes = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(response_bytes)

    def _send_error_json(self, message: str, status_code: int = 400):
        self._send_json({"error": True, "message": message}, status_code)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        # 1. API Endpoints
        if path == "/api/health":
            self.handle_health()
            return
        elif path == "/api/staff":
            self._send_json({"staff": STAFF_MEMBERS})
            return
        elif path == "/api/sources":
            self.handle_get_sources()
            return
        elif path.startswith("/api/companies/") and path.endswith("/proposal"):
            # /api/companies/<inn>/proposal
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[1] == "companies" and parts[3] == "proposal":
                inn = parts[2]
                self._send_json(generate_grounded_proposal(inn))
                return
        elif path.startswith("/api/companies/"):
            # /api/companies/<inn>
            inn = path.strip("/").split("/")[-1]
            profile = get_company_profile_and_timeline(inn)
            self._send_json(profile)
            return
        elif path == "/api/saved-searches":
            self.handle_get_saved_searches()
            return
        elif path == "/api/sync/logs":
            self.handle_get_sync_logs()
            return
        elif path == "/api/eimzo/status":
            from app.eimzo_auth import EImzoAuthManager
            daemon_info = EImzoAuthManager.check_daemon()
            sess_info = EImzoAuthManager.get_session()
            self._send_json({"daemon": daemon_info, "session": sess_info})
            return
        elif path == "/api/export":
            self.handle_export(query_params)
            return
        elif path == "/api/auth/me":
            from app.auth import validate_token
            auth_h = self.headers.get("Authorization", "")
            token = auth_h[7:].strip() if auth_h.startswith("Bearer ") else query_params.get("token", [""])[0]
            user = validate_token(token) if token else None
            self._send_json({"authenticated": bool(user), "user": user})
            return
        elif path == "/api/admin/stats":
            from app.auth import get_admin_stats
            self._send_json({"stats": get_admin_stats()})
            return
        elif path == "/api/admin/tasks":
            from app.auth import get_all_tasks
            self._send_json({"tasks": get_all_tasks()})
            return
        elif path == "/api/gemini/status":
            from app.gemini_service import get_gemini_api_key
            has_key = bool(get_gemini_api_key())
            self._send_json({"has_key": has_key, "model": "gemini-1.5-flash", "mode": "Live Google Gemini API" if has_key else "Heuristic IT Advisor"})
            return

        # 2. Static File Serving
        self.serve_static_file(path)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
        
        body = {}
        if body_bytes:
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except Exception as e:
                self._send_error_json(f"Noto'g'ri JSON format: {str(e)}", 400)
                return

        if path == "/api/auth/login":
            from app.auth import authenticate_user
            uname = body.get("username", "")
            passwd = body.get("password", "")
            res = authenticate_user(uname, passwd)
            if res:
                self._send_json({"success": True, "token": res["token"], "user": res["user"]})
            else:
                self._send_error_json("Login yoki parol noto'g'ri kiritildi.", 401)
            return
        elif path == "/api/auth/logout":
            from app.auth import logout_user
            auth_h = self.headers.get("Authorization", "")
            token = auth_h[7:].strip() if auth_h.startswith("Bearer ") else body.get("token", "")
            if token:
                logout_user(token)
            self._send_json({"success": True, "message": "Tizimdan muvaffaqiyatli chiqildi"})
            return
        elif path == "/api/auth/change-password":
            from app.auth import validate_token, change_password
            auth_h = self.headers.get("Authorization", "")
            token = auth_h[7:].strip() if auth_h.startswith("Bearer ") else body.get("token", "")
            user = validate_token(token) if token else None
            if not user:
                self._send_error_json("Avtorizatsiyadan o'tilmagan", 401)
                return
            old_pwd = body.get("old_password", "")
            new_pwd = body.get("new_password", "")
            ok, msg = change_password(user["username"], old_pwd, new_pwd)
            if ok:
                self._send_json({"success": True, "message": msg})
            else:
                self._send_error_json(msg, 400)
            return
        elif path == "/api/admin/tasks/status":
            from app.auth import update_task_status
            task_id = body.get("task_id")
            new_status = body.get("status")
            if task_id and new_status:
                ok = update_task_status(task_id, new_status)
                self._send_json({"success": ok})
            else:
                self._send_error_json("task_id va status talab qilinadi", 400)
            return
        elif path == "/api/gemini/analyze":
            from app.gemini_service import analyze_lot_with_gemini
            lot_id = str(body.get("lot_id") or body.get("id") or body.get("lot_number") or "")
            res = analyze_lot_with_gemini(lot_id)
            self._send_json(res)
            return
        elif path == "/api/gemini/key":
            from app.gemini_service import set_gemini_api_key
            key = body.get("api_key", "")
            ok = set_gemini_api_key(key)
            self._send_json({"success": ok, "message": "Gemini API kaliti muvaffaqiyatli saqlandi" if ok else "Xatolik"})
            return
        elif path == "/api/search":
            self.handle_search(body)
            return
        elif path == "/api/sync/run":
            from app.config import DEFAULT_START_DATE
            res = sync_manager.run_full_sync_cycle(since_date=DEFAULT_START_DATE)
            self._send_json(res)
            return
        elif path == "/api/eimzo/token":
            from app.eimzo_auth import EImzoAuthManager
            token = body.get("token")
            cookie = body.get("cookie")
            tin = body.get("tin", "308904387")
            res = EImzoAuthManager.save_session(token=token, cookie=cookie, tin=tin)
            self._send_json({"success": True, "session": res, "message": "E-IMZO sessiyasi muvaffaqiyatli saqlandi"})
            return
        elif path == "/api/eimzo/clear":
            from app.eimzo_auth import EImzoAuthManager
            res = EImzoAuthManager.clear_session()
            self._send_json({"success": True, "session": res, "message": "E-IMZO sessiyasi tozalandi"})
            return
        elif path.startswith("/api/companies/") and path.endswith("/assign"):
            # /api/companies/<inn>/assign
            parts = path.strip("/").split("/")
            inn = parts[2]
            staff_id = body.get("staff_id")
            if not staff_id:
                self._send_error_json("staff_id parametri kiritilmadi", 400)
                return
            res = assign_staff(inn, staff_id)
            self._send_json(res)
            return
        elif path.startswith("/api/companies/") and path.endswith("/task"):
            # /api/companies/<inn>/task
            parts = path.strip("/").split("/")
            inn = parts[2]
            title = body.get("task_title", "Mijoz bilan aloqa")
            task_type = body.get("task_type", "TAKTAK_TAYYORLASH")
            assigned_staff_id = body.get("assigned_staff_id")
            lot_id = body.get("lot_id")
            proposal_summary = body.get("proposal_summary")
            res = create_sales_task(
                inn=inn,
                task_title=title,
                task_type=task_type,
                assigned_staff_id=assigned_staff_id,
                lot_id=lot_id,
                proposal_summary=proposal_summary
            )
            self._send_json(res)
            return
        elif path.startswith("/api/companies/") and path.endswith("/bitrix"):
            # /api/companies/<inn>/bitrix
            parts = path.strip("/").split("/")
            inn = parts[2]
            title = body.get("title", "IT Dasturiy ta'minot litsenziyasi")
            amount = float(body.get("amount", 0.0))
            res = push_to_bitrix24(inn, title, amount)
            self._send_json(res)
            return
        elif path.startswith("/api/sources/") and path.endswith("/sync"):
            # /api/sources/<id>/sync
            parts = path.strip("/").split("/")
            source_id = parts[2]
            self.handle_sync_source(source_id)
            return
        elif path == "/api/saved-searches":
            self.handle_save_search(body)
            return

        self._send_error_json("Endpoint topilmadi", 404)

    def handle_health(self):
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM lots;")
            lot_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM companies;")
            company_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM contract_items;")
            items_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sources;")
            source_count = cursor.fetchone()[0]

        self._send_json({
            "status": "online",
            "message": "Softy Platforma backend faol",
            "total_lots": lot_count,
            "total_companies": company_count,
            "total_contract_items": items_count,
            "configured_sources": source_count,
            "platforms": PLATFORMS
        })

    def handle_search(self, body: Dict[str, Any]):
        try:
            results = execute_search(body)
            self._send_json(results)
        except Exception as e:
            self._send_error_json(f"Qidiruvda xatolik: {str(e)}", 500)

    def handle_get_sources(self):
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sources ORDER BY id ASC;")
            rows = [dict(r) for r in cursor.fetchall()]

            # Count lots per source
            cursor.execute("SELECT platform_id, COUNT(*) as count FROM lots GROUP BY platform_id;")
            lot_counts = {r["platform_id"]: r["count"] for r in cursor.fetchall()}

            for r in rows:
                sid = r["id"]
                r["lot_count"] = lot_counts.get(sid, 0)
                # Check adapter
                adapter = get_adapter(sid)
                status_info = adapter.get_status()
                r["adapter_status"] = status_info["status"]
                r["adapter_description"] = status_info["description"]
                r["is_fallback"] = status_info.get("is_fallback", False)

        self._send_json({"sources": rows})

    def handle_sync_source(self, source_id: str):
        adapter = get_adapter(source_id)
        res = adapter.fetch_updates(since_date="2026-01-01")
        self._send_json(res)

    def handle_get_saved_searches(self):
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM saved_searches ORDER BY created_at DESC;")
            searches = []
            for r in cursor.fetchall():
                d = dict(r)
                d["title"] = d.get("name") or d.get("title")
                d["query_text"] = d.get("search_query") or d.get("query_text")
                filter_json_str = d.get("filters_json") or d.get("filter_params_json")
                if filter_json_str:
                    try:
                        d["filter_params"] = json.loads(filter_json_str)
                    except Exception:
                        d["filter_params"] = {}
                searches.append(d)
        self._send_json({"saved_searches": searches})

    def handle_save_search(self, body: Dict[str, Any]):
        from datetime import datetime
        title = body.get("title") or body.get("name", "Saqlangan qidiruv")
        query_text = body.get("query_text") or body.get("search_query", "")
        filter_params = body.get("filter_params") or body.get("filters", {})
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO saved_searches (name, search_query, filters_json, created_at)
            VALUES (?, ?, ?, ?);
            """, (title, query_text, json.dumps(filter_params, ensure_ascii=False), now_str))
            new_id = cursor.lastrowid

        self._send_json({"success": True, "id": new_id, "title": title})

    def handle_get_sync_logs(self):
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, platform_id, sync_start, sync_end, records_added, records_updated, status, error_message
            FROM sync_logs ORDER BY id DESC LIMIT 20;
            """)
            logs = [dict(r) for r in cursor.fetchall()]
        self._send_json({"sync_logs": logs})

    def handle_export(self, params: Dict[str, List[str]]):
        filters = {}
        for k, v in params.items():
            if len(v) == 1:
                filters[k] = v[0]
            else:
                filters[k] = v

        if "platforms" in filters and isinstance(filters["platforms"], str):
            filters["platforms"] = [p.strip() for p in filters["platforms"].split(",") if p.strip()]

        if "include_missing_dates" in filters:
            filters["include_missing_dates"] = str(filters["include_missing_dates"]).lower() in ["true", "1"]

        if "has_contract" in filters:
            filters["has_contract"] = str(filters["has_contract"]).lower() in ["true", "1"]

        format_type = filters.get("format", "xlsx").lower()
        content_data, media_type, filename = export_data(filters, format_type=format_type)
        if isinstance(content_data, str):
            resp_bytes = content_data.encode("utf-8")
        else:
            resp_bytes = content_data

        self.send_response(200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(resp_bytes)

    def serve_static_file(self, req_path: str):
        if req_path in ["", "/"]:
            file_path = FRONTEND_DIR / "index.html"
        else:
            rel_path = req_path.lstrip("/")
            file_path = FRONTEND_DIR / rel_path

        try:
            resolved_path = file_path.resolve()
            if not str(resolved_path).startswith(str(FRONTEND_DIR.resolve())):
                self._send_error_json("Ruxsat berilmagan fayl yo'li", 403)
                return
        except Exception:
            self._send_error_json("Fayl topilmadi", 404)
            return

        if not resolved_path.is_file():
            fallback = FRONTEND_DIR / "index.html"
            if fallback.is_file():
                resolved_path = fallback
            else:
                self._send_error_json("Fayl topilmadi", 404)
                return

        mime_type, _ = mimetypes.guess_type(str(resolved_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        try:
            with open(resolved_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{mime_type}; charset=utf-8" if "text" in mime_type or "javascript" in mime_type or "json" in mime_type else mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_error_json(f"Faylni o'qishda xatolik: {str(e)}", 500)

def run_server(host: str = HOST, port: int = PORT):
    init_db()
    # Start background daily sync scheduler (once per 24 hours at 03:00)
    sync_manager.start_background_scheduler()

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, SoftyRequestHandler)
    print(f"=====================================================", flush=True)
    print(f"  SOFTY PLATFORMA — Server ishga tushdi:", flush=True)
    print(f"  Local:  http://127.0.0.1:{port}", flush=True)
    print(f"  Domain: http://{DOMAIN}:{port} (yoki http://{DOMAIN})", flush=True)
    print(f"  Davlat xaridlari qidiruvi va yagona mijozlar bazasi", flush=True)
    print(f"  Baza boshlanish sanasi: 2024-01-01 (1-yanvar 2024)", flush=True)
    print(f"  Hostinger integratsiyasi: tender.softy.uz (62.72.50.47)", flush=True)
    print(f"  Kunlik anti-blocking sinxronizatsiya: FAOL (har kuni 03:00 da)", flush=True)
    print(f"=====================================================", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer to'xtatildi.", flush=True)
        sync_manager.stop_background_scheduler()
        httpd.server_close()

if __name__ == "__main__":
    run_server()
