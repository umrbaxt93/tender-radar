"""
Softy Platforma — Email OTP Service
Login paytida umrbaxt93@gmail.com ga 6 raqamli tasdiqlash kodi yuborish.
Hostinger sendmail va SMTP orqali ishlaydi.
"""

import os
import random
import string
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from app.database import db_session

OTP_EMAIL = "umrbaxt93@gmail.com"
GMAIL_USER = os.environ.get("GMAIL_USER", "umrbaxt93@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "security@softy.uz")

OTP_LENGTH = 6
OTP_EXPIRE_MINUTES = 5


def init_approval_table():
    """otp_codes jadvalini yaratish."""
    with db_session() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0
        );""")
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_otp_user ON otp_codes (username, used, expires_at);")
        except Exception:
            pass


def _generate_code() -> str:
    return ''.join(random.choices(string.digits, k=OTP_LENGTH))


def create_email_otp(username: str) -> str:
    """
    6 raqamli kod yaratib, umrbaxt93@gmail.com ga yuborish va DB ga saqlash.
    """
    init_approval_table()
    code = _generate_code()
    now = datetime.now()
    expires = now + timedelta(minutes=OTP_EXPIRE_MINUTES)

    with db_session() as conn:
        conn.execute("UPDATE otp_codes SET used = 1 WHERE username = ? AND used = 0;", (username,))
        conn.execute("""
        INSERT INTO otp_codes (username, code, created_at, expires_at, used)
        VALUES (?, ?, ?, ?, 0);""", (
            username, code,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            expires.strftime("%Y-%m-%d %H:%M:%S")
        ))

    _send_otp_email(username, code, now)
    return code


def _send_otp_email(username: str, code: str, now: datetime) -> bool:
    """OTP kodini umrbaxt93@gmail.com ga yuborish."""
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    subject = f"🔐 Softy Kirish Kodi: {code}"
    
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; background-color: #f8fafc;">
  <div style="background: linear-gradient(135deg, #1e1b4b, #1e3a8a, #0f172a); padding: 28px 24px; border-radius: 16px; text-align: center; color: white;">
    <div style="font-size: 32px; margin-bottom: 8px;">🛡️</div>
    <h1 style="margin: 0; font-size: 20px; font-weight: 800; letter-spacing: 0.5px;">SOFTY PLATFORMA</h1>
    <p style="margin: 6px 0 0; font-size: 13px; color: #93c5fd;">2-Bosqichli Xavfsizlik Tasdiqlash</p>
  </div>

  <div style="background: white; border: 1px solid #e2e8f0; border-radius: 16px; padding: 28px 24px; margin-top: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
    <p style="margin: 0 0 12px; font-size: 14px; color: #334155;">Hurmatli <strong>{username}</strong>,</p>
    <p style="margin: 0 0 20px; font-size: 14px; color: #475569; line-height: 1.5;">
      Softy Platformaga kirish uchun quyidagi 6 xonali tasdiqlash kodini kiriting:
    </p>

    <div style="text-align: center; margin: 24px 0;">
      <div style="display: inline-block; background: #eff6ff; border: 2px dashed #3b82f6; border-radius: 14px; padding: 16px 36px;">
        <span style="font-family: 'SF Mono', Consolas, Monaco, monospace; font-size: 38px; font-weight: 800; letter-spacing: 12px; color: #1e3a8a;">{code}</span>
      </div>
    </div>

    <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px 14px; border-radius: 8px; margin-bottom: 20px;">
      <p style="margin: 0; font-size: 12px; color: #92400e; font-weight: 600;">
        ⏱ Kod 5 daqiqa davomida amal qiladi.
      </p>
      <p style="margin: 4px 0 0; font-size: 11px; color: #b45309;">
        Agar siz kirishga urinmagan bo'lsangiz, ushbu xabarni e'tiborsiz qoldiring.
      </p>
    </div>

    <div style="font-size: 11px; color: #94a3b8; border-top: 1px solid #f1f5f9; padding-top: 14px; text-align: center;">
      Toshkent vaqti: {now_str} | IP xavfsizlik himoyasi faol
    </div>
  </div>
</body>
</html>"""

    # 1. Usul: /usr/sbin/sendmail (Hostinger serverida kafolatlangan)
    if os.path.exists("/usr/sbin/sendmail"):
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Softy Xavfsizlik <{SENDER_EMAIL}>"
            msg["To"] = OTP_EMAIL
            msg.attach(MIMEText(html, "html", "utf-8"))

            proc = subprocess.Popen(["/usr/sbin/sendmail", "-t", "-oi"], stdin=subprocess.PIPE)
            proc.communicate(msg.as_bytes())
            if proc.returncode == 0:
                print(f"[OTP] sendmail orqali {OTP_EMAIL} ga muvaffaqiyatli yuborildi.")
                return True
        except Exception as e:
            print(f"[OTP] sendmail xatosi: {e}")

    # 2. Usul: Gmail SMTP (agar app password berilgan bo'lsa)
    if GMAIL_APP_PASSWORD:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = GMAIL_USER
            msg["To"] = OTP_EMAIL
            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as srv:
                srv.login(GMAIL_USER, GMAIL_APP_PASSWORD)
                srv.sendmail(GMAIL_USER, OTP_EMAIL, msg.as_string())
            print(f"[OTP] SMTP orqali {OTP_EMAIL} ga yuborildi.")
            return True
        except Exception as e:
            print(f"[OTP] SMTP xatosi: {e}")

    print(f"[OTP LOCAL FALLBACK] Kod: {code} (Email: {OTP_EMAIL})")
    return True


def verify_email_otp(username: str, code: str) -> bool:
    """OTP kodini tekshirish."""
    init_approval_table()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_code = (code or "").strip()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id FROM otp_codes
        WHERE username = ? AND code = ? AND used = 0 AND expires_at > ?
        ORDER BY id DESC LIMIT 1;""", (username, clean_code, now_str))
        row = cursor.fetchone()
        if not row:
            return False
        conn.execute("UPDATE otp_codes SET used = 1 WHERE id = ?;", (row[0],))
        return True


def send_login_alert(username: str, ip: str = ""):
    """Tizimga muvaffaqiyatli kirilganda emailga xabar yuborish (kirishni to'xtatmaydi)."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"🛡️ Softy Kirish Bildirishnomasi: {username}"
    html = f"""<!DOCTYPE html>
<html>
<body style="font-family: sans-serif; padding: 20px; background: #f8fafc; color: #1e293b;">
  <div style="background: white; border-radius: 12px; padding: 24px; border: 1px solid #e2e8f0; max-width: 500px;">
    <h2 style="color: #1e3a8a; margin-top: 0;">✅ Tizimga Muvaffaqiyatli Kirildi</h2>
    <p>Hurmatli Umidjon,</p>
    <p>Softy Platformaga quyidagi hisob orqali kirildi:</p>
    <ul>
      <li><strong>Foydalanuvchi:</strong> {username}</li>
      <li><strong>Vaqt:</strong> {now_str}</li>
      <li><strong>IP:</strong> {ip or 'Nomaʼlum'}</li>
    </ul>
    <p style="font-size: 12px; color: #64748b;">Agar bu siz bo'lmasangiz, darhol parolingizni o'zgartiring.</p>
  </div>
</body>
</html>"""
    if os.path.exists("/usr/sbin/sendmail"):
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Softy Xavfsizlik <{SENDER_EMAIL}>"
            msg["To"] = OTP_EMAIL
            msg.attach(MIMEText(html, "html", "utf-8"))
            proc = subprocess.Popen(["/usr/sbin/sendmail", "-t", "-oi"], stdin=subprocess.PIPE)
            proc.communicate(msg.as_bytes(), timeout=5)
        except Exception as e:
            print(f"[ALERT] sendmail error: {e}")

