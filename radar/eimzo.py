"""E-IMZO Authentication Bridge & Session Manager for Tender Radar.

Allows connecting to E-Birja and government procurement portals using
the user's electronic digital signature (E-IMZO / E-Kalit).
"""

from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_SESSION_FILE = Path(__file__).resolve().parent.parent / "data" / "eimzo_session.json"
EBIRJA_API_BASE = "https://xarid-api.ebirja.uz"
EIMZO_PORTS = (64443, 64646, 17743)


class EImzoManager:
    """Manages local E-IMZO daemon discovery, challenge acquisition, and session tokens."""

    def __init__(self, session_file: Path | None = None, api_base: str = EBIRJA_API_BASE) -> None:
        self.session_file = session_file or DEFAULT_SESSION_FILE
        self.api_base = api_base.rstrip("/")

    def check_daemon(self) -> dict[str, Any]:
        """Check if local E-IMZO daemon is running on standard ports."""
        ctx = ssl._create_unverified_context()
        for port in EIMZO_PORTS:
            scheme = "https" if port == 64443 else "http"
            url = f"{scheme}://127.0.0.1:{port}/"
            try:
                req = urllib.request.Request(
                    url,
                    headers={"Origin": "https://ebirja.uz", "User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(req, context=ctx, timeout=1.5) as resp:
                    return {
                        "running": True,
                        "port": port,
                        "status_code": resp.getcode(),
                        "message": f"E-IMZO dasturi faol ({port}-portda)",
                    }
            except urllib.error.HTTPError as exc:
                if exc.code in (400, 403, 404, 405, 200):
                    return {
                        "running": True,
                        "port": port,
                        "status_code": exc.code,
                        "message": f"E-IMZO dasturi faol ({port}-portda)",
                    }
            except Exception:
                continue

        return {
            "running": False,
            "port": None,
            "message": "E-IMZO dasturi (E-IMZO.app) lokal portlarda topilmadi.",
        }

    def get_challenge(self) -> dict[str, Any]:
        """Request a fresh authentication challenge from E-Birja API."""
        url = f"{self.api_base}/auth/user/challenge"
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                res = data.get("result", {})
                if isinstance(res, str):
                    try:
                        res = json.loads(res)
                    except Exception:
                        pass
                challenge = res.get("challenge") if isinstance(res, dict) else None
                ttl = res.get("ttl", 120) if isinstance(res, dict) else 120
                return {
                    "status": "ok",
                    "challenge": challenge,
                    "ttl": ttl,
                    "raw": data,
                }
        except Exception as exc:
            log.warning("Failed to get challenge from %s: %s", url, exc)
            return {"status": "error", "error": str(exc), "challenge": None}

    def verify_and_login(self, pkcs7_signature: str) -> dict[str, Any]:
        """Submit the signed PKCS#7 challenge to exchange for an E-Birja session token."""
        url = f"{self.api_base}/auth/user/frontend-timestamp"
        ctx = ssl._create_unverified_context()
        payload = json.dumps({"pkcs7": pkcs7_signature}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                token = data.get("result", {}).get("token") or data.get("token")
                user = data.get("result", {}).get("user") or data.get("user", {})
                tin = user.get("tin") or user.get("inn") or "308904387"
                if token:
                    self.save_session(token=token, tin=tin, user_data=user)
                return {"status": "ok", "token": token, "user": user, "data": data}
        except Exception as exc:
            log.error("E-IMZO verification failed: %s", exc)
            return {"status": "error", "error": str(exc)}

    def get_session(self) -> dict[str, Any]:
        """Read currently stored E-IMZO session."""
        if self.session_file.exists():
            try:
                with open(self.session_file, encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception as exc:
                log.warning("Could not read session file %s: %s", self.session_file, exc)
        return {
            "authenticated": False,
            "token": None,
            "cookie": None,
            "tin": "308904387",
            "last_updated": None,
        }

    def save_session(
        self,
        token: str | None = None,
        cookie: str | None = None,
        tin: str = "308904387",
        user_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist session token and credentials."""
        session_data = {
            "authenticated": bool(token or cookie),
            "token": token.strip() if token else None,
            "cookie": cookie.strip() if cookie else None,
            "tin": tin.strip() if tin else "308904387",
            "user": user_data or {},
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.session_file, "w", encoding="utf-8") as fh:
            json.dump(session_data, fh, ensure_ascii=False, indent=2)
        return session_data

    def clear_session(self) -> dict[str, Any]:
        """Clear active session credentials."""
        return self.save_session(token=None, cookie=None)

    def get_auth_headers(self) -> dict[str, str]:
        """Return HTTP headers with Bearer token if session is valid."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Accept": "application/json",
        }
        session = self.get_session()
        if session.get("authenticated") and session.get("token"):
            headers["Authorization"] = f"Bearer {session['token']}"
            headers["user-key"] = session["token"]
        if session.get("cookie"):
            headers["Cookie"] = session["cookie"]
        return headers
