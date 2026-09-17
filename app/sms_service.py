"""
Softy Platforma — SMS Service (Eskiz.uz OTP)
O'zbekistondagi Eskiz.uz SMS gateway orqali bir martalik parol yuborish.
"""

import os
import random
import string
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from app.database import db_session

ESKIZ_EMAIL = os.environ.get("ESKIZ_EMAIL", "")
ESKIZ_PASSWORD = os.environ.get("ESKIZ_PASSWORD", "")
ESKIZ_BASE_URL = "https://notify.eskiz.uz/api"
ESKIZ_SENDER = os.environ.get("ESKIZ_SENDER", "Softy")

OTP_LENGTH = 6
OTP_EXPIRE_MINUTES = 5


def init_sms_table():
    with db_session() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sms_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            phone TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0
        );""")
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sms_username
        ON sms_codes (username, used, expires_at);""")


def generate_otp() -> str:
    return ''.join(random.choices(string.digits, k=OTP_LENGTH))


def _get_eskiz_token() -> str:
    if not ESKIZ_EMAIL or not ESKIZ_PASSWORD:
        return None
    try:
        data = urllib.parse.urlencode({
            "email": ESKIZ_EMAIL,
            "password": ESKIZ_PASSWORD
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{ESKIZ_BASE_URL}/auth/login", data=data, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("data", {}).get("token")
    except Exception as e:
        print(f"[SMS] Eskiz token xatoligi: {e}")
        return None


def send_sms(phone: str, message: str) -> bool:
    token = _get_eskiz_token()
    if not token:
        print(f"[SMS] Token yo'q — SMS yuborilmadi ({phone})")
        return False
    phone = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if not phone.startswith("998"):
        phone = "998" + (phone[1:] if phone.startswith("0") else phone)
    try:
        data = urllib.parse.urlencode({
            "mobile_phone": phone,
            "message": message,
            "from": ESKIZ_SENDER,
            "callback_url": ""
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{ESKIZ_BASE_URL}/message/sms/send", data=data, method="POST",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            status = result.get("status", "")
            print(f"[SMS] Yuborildi {phone}: {status}")
            return status in ("waiting", "success", "sent")
    except Exception as e:
        print(f"[SMS] Yuborish xatoligi: {e}")
        return False


def send_sms_code(username: str, phone: str) -> bool:
    init_sms_table()
    code = generate_otp()
    now = datetime.now()
    expires = now + timedelta(minutes=OTP_EXPIRE_MINUTES)
    with db_session() as conn:
        conn.execute("UPDATE sms_codes SET used = 1 WHERE username = ? AND used = 0;", (username,))
        conn.execute("""
        INSERT INTO sms_codes (username, phone, code, created_at, expires_at, used)
        VALUES (?, ?, ?, ?, ?, 0);""", (
            username, phone, code,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            expires.strftime("%Y-%m-%d %H:%M:%S")
        ))
    message = f"Softy Platforma tasdiqlash kodi: {code}\nAmal qilish muddati: {OTP_EXPIRE_MINUTES} daqiqa."
    success = send_sms(phone, message)
    if not success:
        print(f"[SMS FALLBACK] {username} uchun kod: {code}")
    return True  # Always return True - code is saved to DB


def verify_sms_code(username: str, code: str) -> bool:
    init_sms_table()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id FROM sms_codes
        WHERE username = ? AND code = ? AND used = 0 AND expires_at > ?
        ORDER BY id DESC LIMIT 1;""", (username, code.strip(), now_str))
        row = cursor.fetchone()
        if not row:
            return False
        conn.execute("UPDATE sms_codes SET used = 1 WHERE id = ?;", (row[0],))
        return True


def cleanup_expired_codes():
    try:
        with db_session() as conn:
            conn.execute("DELETE FROM sms_codes WHERE expires_at < ?;",
                         (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    except Exception:
        pass
