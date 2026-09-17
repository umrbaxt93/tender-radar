"""
Softy Platforma — Authentication and User Management Module
Admin (email 2FA) + Member (SMS 2FA) kirish tizimi.
"""

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from app.database import db_session

DEFAULT_ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "")
SESSION_DURATION_DAYS = 7

# IT kategoriyalari (member uchun filter)
IT_KEYWORDS = [
    "программ", "software", "dastur", "it ", "компьютер", "kompyuter",
    "сервер", "server", "техническ", "texnik", "ноутбук", "noutbuk",
    "принтер", "printer", "интернет", "internet", "сеть", "network",
    "лицензи", "litsenziya", "антивирус", "antivirus", "камера", "kamera",
    "проектор", "proyektor", "мониторинг", "monitoring", "облако", "cloud",
    "телекоммуникац", "telekommunikatsiya", "1с", "1c ", "erp", "crm",
    "телефон", "telefon", "планшет", "planshet", "картридж", "kartridj",
    "модем", "modem", "роутер", "router", "коммутатор", "switch",
    "жесткий диск", "qattiq disk", "ssd", "hdd", "usb", "флеш",
    "видеонаблюден", "видеокамер", "ccтv", "cctv", "ксерокс",
    "сканер", "skaner", "ups", "бесперебойник", "аккумулятор",
    "кабель", "kabel", "ит ", "ахборот технологи", "axborot texnologiya",
    "разработк", "ishlab chiqish", "веб", "web", "mobile", "мобильн",
    "программирован", "dasturlash", "система", "tizim", "informatika"
]


def hash_password(password: str, salt: str = None) -> str:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash or "$" not in stored_hash:
        return False
    salt, original_hash = stored_hash.split("$", 1)
    test_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return secrets.compare_digest(original_hash, test_hash)


def init_auth_tables():
    with db_session() as conn:
        # admin_users — phone va role ustunlari bilan
        conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            role TEXT DEFAULT 'admin',
            phone TEXT,
            email TEXT,
            sms_2fa INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            last_login TEXT
        );""")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (username) REFERENCES admin_users (username) ON DELETE CASCADE
        );""")

        # Migrate: phone ustunini qo'shish (agar yo'q bo'lsa)
        try:
            conn.execute("ALTER TABLE admin_users ADD COLUMN phone TEXT;")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE admin_users ADD COLUMN email TEXT;")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE admin_users ADD COLUMN sms_2fa INTEGER DEFAULT 0;")
        except Exception:
            pass

        # Default admin
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM admin_users WHERE username = ?;", (DEFAULT_ADMIN_USER,))
        if not cursor.fetchone():
            pwd_hash = hash_password(DEFAULT_ADMIN_PASS or "softy2026!")
            conn.execute("""
            INSERT INTO admin_users (username, password_hash, full_name, role, sms_2fa, created_at)
            VALUES (?, ?, ?, 'admin', 0, ?);""", (
                DEFAULT_ADMIN_USER, pwd_hash, "Bosh Administrator",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

        # Umidjon account
        cursor.execute("SELECT id FROM admin_users WHERE username = 'umidjon';")
        if not cursor.fetchone():
            pwd_hash2 = hash_password("softy2026!")
            conn.execute("""
            INSERT INTO admin_users (username, password_hash, full_name, role, sms_2fa, created_at)
            VALUES ('umidjon', ?, 'Umidjon (Softy LLC)', 'admin', 0, ?);""", (
                pwd_hash2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))


def authenticate_user(username: str, password: str):
    """
    Foydalanuvchi login+parolni tekshirish.
    Returns: user dict (token yo'q — keyingi bosqichda yaratiladi)
    """
    init_auth_tables()
    username = (username or "").strip()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, username, password_hash, full_name, role, phone, sms_2fa
        FROM admin_users WHERE username = ?;""", (username,))
        row = cursor.fetchone()
        if not row:
            return None
        user_id, uname, pwd_hash, full_name, role, phone, sms_2fa = row
        if not verify_password(password, pwd_hash):
            return None
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE admin_users SET last_login = ? WHERE id = ?;", (now_str, user_id))
        return {
            "id": user_id,
            "username": uname,
            "full_name": full_name,
            "role": role,
            "phone": phone,
            "sms_2fa": bool(sms_2fa)
        }


def create_session_for_user(username: str) -> dict:
    """Session token yaratish (2FA muvaffaqiyatdan keyin)."""
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, username, full_name, role
        FROM admin_users WHERE username = ?;""", (username,))
        row = cursor.fetchone()
        if not row:
            return None
        user_id, uname, full_name, role = row
        token = secrets.token_hex(32)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        expires_at = (datetime.now() + timedelta(days=SESSION_DURATION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
        INSERT INTO admin_sessions (token, username, created_at, expires_at)
        VALUES (?, ?, ?, ?);""", (token, uname, now_str, expires_at))
        return {
            "token": token,
            "user": {"id": user_id, "username": uname, "full_name": full_name, "role": role},
            "expires_at": expires_at
        }


def validate_token(token: str):
    if not token:
        return None
    init_auth_tables()
    with db_session() as conn:
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        SELECT s.token, s.username, u.full_name, u.role, s.expires_at
        FROM admin_sessions s
        JOIN admin_users u ON s.username = u.username
        WHERE s.token = ? AND s.expires_at > ?;""", (token, now_str))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "token": row[0],
            "username": row[1],
            "full_name": row[2],
            "role": row[3],
            "expires_at": row[4]
        }


def logout_user(token: str):
    if not token:
        return False
    with db_session() as conn:
        conn.execute("DELETE FROM admin_sessions WHERE token = ?;", (token,))
        return True


def change_password(username: str, old_pass: str, new_pass: str):
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, password_hash FROM admin_users WHERE username = ?;", (username,))
        row = cursor.fetchone()
        if not row:
            return False, "Foydalanuvchi topilmadi"
        user_id, pwd_hash = row
        if not verify_password(old_pass, pwd_hash):
            return False, "Eski parol noto'g'ri kiritildi"
        if not new_pass or len(new_pass) < 6:
            return False, "Yangi parol kamida 6 belgidan iborat bo'lishi kerak"
        conn.execute("UPDATE admin_users SET password_hash = ? WHERE id = ?;",
                     (hash_password(new_pass), user_id))
        return True, "Parol muvaffaqiyatli o'zgartirildi"


def create_member_user(username: str, password: str, full_name: str, phone: str) -> dict:
    """Yangi member foydalanuvchi yaratish."""
    init_auth_tables()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM admin_users WHERE username = ?;", (username,))
        if cursor.fetchone():
            return {"success": False, "error": "Bu username allaqachon mavjud"}
        pwd_hash = hash_password(password)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
        INSERT INTO admin_users (username, password_hash, full_name, role, phone, sms_2fa, created_at)
        VALUES (?, ?, ?, 'member', ?, 1, ?);""", (
            username, pwd_hash, full_name, phone, now_str
        ))
        return {"success": True, "message": f"'{full_name}' member qo'shildi"}


def get_all_users() -> list:
    """Barcha foydalanuvchilar ro'yxati."""
    init_auth_tables()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, username, full_name, role, phone, sms_2fa, created_at, last_login
        FROM admin_users ORDER BY role, username;""")
        rows = cursor.fetchall()
        return [
            {
                "id": r[0], "username": r[1], "full_name": r[2],
                "role": r[3], "phone": r[4], "sms_2fa": bool(r[5]),
                "created_at": r[6], "last_login": r[7]
            }
            for r in rows
        ]


def is_it_related(title: str, category: str = "") -> bool:
    """IT yo'nalishiga tegishliligini tekshirish."""
    text = ((title or "") + " " + (category or "")).lower()
    return any(kw in text for kw in IT_KEYWORDS)


def get_admin_stats():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM lots;")
        total_lots = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM companies;")
        total_companies = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(contract_amount), 0) FROM lots WHERE has_contract = 1;")
        c_row = cursor.fetchone()
        total_contracts = c_row[0]
        total_contract_sum = c_row[1]
        cursor.execute("SELECT platform_id, COUNT(*) FROM lots GROUP BY platform_id;")
        platform_counts = dict(cursor.fetchall())
        cursor.execute("SELECT * FROM sources ORDER BY id ASC;")
        sources = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) FROM tasks_and_proposals;")
        total_tasks = cursor.fetchone()[0]
        cursor.execute("SELECT * FROM sync_logs ORDER BY id DESC LIMIT 10;")
        recent_syncs = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) FROM admin_users;")
        users_count = cursor.fetchone()[0]
        return {
            "total_lots": total_lots,
            "total_companies": total_companies,
            "total_contracts": total_contracts,
            "total_contract_sum": total_contract_sum,
            "platform_counts": platform_counts,
            "sources": sources,
            "total_tasks": total_tasks,
            "recent_syncs": recent_syncs,
            "users_count": users_count
        }


def get_all_tasks():
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT t.*, c.name as company_name, c.phone as company_phone
        FROM tasks_and_proposals t
        LEFT JOIN companies c ON t.company_inn = c.inn
        ORDER BY t.id DESC LIMIT 100;""")
        return [dict(r) for r in cursor.fetchall()]


def update_task_status(task_id: int, new_status: str):
    with db_session() as conn:
        conn.execute("UPDATE tasks_and_proposals SET status = ? WHERE id = ?;", (new_status, task_id))
        return True
