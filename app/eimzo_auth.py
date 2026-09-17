"""
Softy Platforma — E-IMZO Authentication Bridge & Session Manager
Foydalanuvchining elektron raqamli imzosi (E-IMZO / E-Kalit) orqali davlat xaridlari
platformalariga xavfsiz va bloklanishlarsiz ulanish mexanizmi.
"""

import os
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
SESSION_FILE = BASE_DIR / "data" / "eimzo_session.json"
EIMZO_LOCAL_URL = "http://127.0.0.1:17743/v1/call"

class EImzoAuthManager:
    """
    E-IMZO orqali autentifikatsiya, sessiya kalitlari va birja platformalari
    uchun xavfsiz sarlavhalar (headers) menejeri.
    """

    @classmethod
    def check_daemon(cls) -> Dict[str, Any]:
        """Lokal kompyuterdagi E-IMZO (127.0.0.1:17743) dasturi holatini tekshirish"""
        try:
            req = urllib.request.Request(
                EIMZO_LOCAL_URL,
                data=b"{}",
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    return {
                        "running": True,
                        "status_code": resp.getcode(),
                        "message": "E-IMZO dasturi faol va ulanishga tayyor (127.0.0.1:17743)"
                    }
            except urllib.error.HTTPError as e:
                if e.code in [400, 405, 200]:
                    return {
                        "running": True,
                        "status_code": e.code,
                        "message": "E-IMZO dasturi faol va ulanishga tayyor (127.0.0.1:17743)"
                    }
                return {"running": False, "status_code": e.code, "message": f"E-IMZO javob kodi: {e.code}"}
        except Exception as ex:
            return {
                "running": False,
                "error": str(ex),
                "message": "E-IMZO dasturi (E-IMZO.app) lokal portda faol emas yoki o'chirilgan."
            }

    @classmethod
    def get_session(cls) -> Dict[str, Any]:
        """Joriy saqlangan E-IMZO sessiyasini o'qish"""
        if SESSION_FILE.exists():
            try:
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "authenticated": False,
            "token": None,
            "cookie": None,
            "tin": "308904387",
            "last_updated": None
        }

    @classmethod
    def save_session(cls, token: Optional[str] = None, cookie: Optional[str] = None, tin: str = "308904387") -> Dict[str, Any]:
        """Yangi E-IMZO sessiya ma'lumotlari yoki elektron kalitni saqlash"""
        session_data = {
            "authenticated": bool(token or cookie),
            "token": token.strip() if token else None,
            "cookie": cookie.strip() if cookie else None,
            "tin": tin.strip() if tin else "308904387",
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        return session_data

    @classmethod
    def clear_session(cls) -> Dict[str, Any]:
        """Sessiyani tozalash"""
        return cls.save_session(token=None, cookie=None)

    @classmethod
    def get_platform_headers(cls, platform_id: str, custom_ua: Optional[str] = None) -> Dict[str, str]:
        """Platformaga so'rov yuborishda E-IMZO sessiyasidan foydalanish"""
        ua = custom_ua or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        headers = {
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en;q=0.7",
            "Connection": "keep-alive"
        }
        session = cls.get_session()
        if session.get("authenticated"):
            if session.get("token"):
                headers["Authorization"] = f"Bearer {session['token']}"
                headers["user-key"] = session["token"]
            if session.get("cookie"):
                headers["Cookie"] = session["cookie"]

        return headers
