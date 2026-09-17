"""
Softy Platforma — Bitrix24 Integration Service
AI/Radar qayta xarid imkoniyatlarini Bitrix24'da Umidjon Fatullaevga (ID: 22) topshiriq qilib yo'naltirish.
Takrorlanishning (dublikat) oldini olish va toza xarid ma'lumotlarini (oldingi yetkazib beruvchi bilan) taqdim etish.
"""

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from app.database import db_session

BITRIX_WEBHOOK = os.environ.get(
    "BITRIX_WEBHOOK",
    "https://softytest.bitrix24.uz/rest/1/m51utd0b79b5s6k4/"
)
UMID_USER_ID = os.environ.get("BITRIX_UMID_ID", "22")  # Umidjon Fatullaev


def init_sent_tasks_table():
    """Bitrix24 ga yuborilgan topshiriqlarni saqlaydigan jadvalni yaratish."""
    with db_session() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_bitrix_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lot_key TEXT NOT NULL UNIQUE,
            procedure_id TEXT,
            customer TEXT,
            title TEXT,
            task_id TEXT,
            sent_at TEXT NOT NULL
        );""")
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_lot_key ON sent_bitrix_tasks(lot_key);")
        except Exception:
            pass


def get_lot_key(lot: dict) -> str:
    """Lot uchun yagona kalit generatsiya qilish."""
    stir = (lot.get("stir") or lot.get("customer_inn") or "").strip()
    proc_id = str(lot.get("procedure_id") or lot.get("lot_id") or "").strip()
    title = (lot.get("title") or lot.get("product_name") or "").strip()[:40]
    return f"{stir}_{proc_id}_{title}".replace(" ", "_")


def is_lot_already_sent(lot_key: str):
    """Lot allaqachon Bitrix24 ga yuborilganligini tekshirish."""
    init_sent_tasks_table()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, sent_at FROM sent_bitrix_tasks WHERE lot_key = ? LIMIT 1;", (lot_key,))
        row = cursor.fetchone()
        if row:
            return {"task_id": row[0], "sent_at": row[1]}
    return None


def mark_lot_as_sent(lot_key: str, proc_id: str, customer: str, title: str, task_id: str):
    """Lotni yuborilganlar jadvaliga qo'shish."""
    init_sent_tasks_table()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO sent_bitrix_tasks (lot_key, procedure_id, customer, title, task_id, sent_at)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (lot_key, proc_id, customer, title, task_id, now_str))


def get_all_sent_task_keys() -> list:
    """Barcha yuborilgan lot kalitlarini olish."""
    init_sent_tasks_table()
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT lot_key FROM sent_bitrix_tasks;")
        return [r[0] for r in cursor.fetchall()]


def _call_bx(method: str, params: dict = None) -> dict:
    """Bitrix24 REST API chaqiruvi (.json qo'shimchasi bilan)."""
    base = BITRIX_WEBHOOK.rstrip('/')
    url = f"{base}/{method}.json"
    body = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def create_radar_task(lot: dict, advice: str = "") -> dict:
    """
    Qayta xarid topshirig'ini Umidjon nomidan Umidjonga Bitrix24 da yaratish.
    Ortiqcha AI matnlarisiz, aniq oldingi yetkazib beruvchi ma'lumotlari bilan.
    Takroriy yuborishni avtomatik ravishda bloklaydi!
    """
    lot_key = get_lot_key(lot)
    existing = is_lot_already_sent(lot_key)
    if existing:
        return {
            "success": False,
            "already_sent": True,
            "task_id": existing["task_id"],
            "message": f"Ushbu topshiriq allaqachon Bitrix24 ga yuborilgan (Topshiriq #{existing['task_id']})!",
            "task_url": f"https://softytest.bitrix24.uz/company/personal/user/{UMID_USER_ID}/tasks/task/view/{existing['task_id']}/"
        }

    title = (lot.get("title") or lot.get("product_name") or "Davlat xaridi loti")[:200]
    customer = lot.get("customer") or lot.get("customer_name") or "Davlat buyurtmachisi"
    stir = lot.get("stir") or lot.get("customer_inn") or "-"
    region = lot.get("region") or "O'zbekiston"
    amount = float(lot.get("amount") or lot.get("deal_sum") or 0)
    renewal_date = lot.get("expected_renewal") or lot.get("contract_end_date") or "2026-yil"
    contact_date = lot.get("contact_by") or "Yaqin kunlarda"
    url = lot.get("source_url") or lot.get("lot_url") or "https://tender.softy.uz"
    
    # Oldingi yetkazib beruvchi (g'olib) ma'lumoti
    prev_supplier = lot.get("previous_supplier") or lot.get("winner_name") or lot.get("supplier_name") or "Aniqlanmagan"
    prev_supplier_stir = lot.get("previous_supplier_stir") or lot.get("winner_inn") or lot.get("supplier_inn") or ""
    prev_supplier_line = f"• STIR: {prev_supplier_stir}" if prev_supplier_stir else ""

    amt_formatted = f"{int(amount):,}".replace(",", " ") if amount else "Noma'lum"

    # Faqat aniq, amaliy biznes ma'lumotlari (hech qanday AI robotic text yoki JSON dumps yo'q)
    description = f"""🏢 BUYURTMACHI MA'LUMOTLARI:
• Tashkilot: {customer}
• STIR (INN): {stir}
• Hudud: {region}
• Xarid ob'ekti: {title}
• Shartnoma summasi: {amt_formatted} so'm
• Kutilayotgan qayta xarid: {renewal_date}
• Murojaat qilish tavsiya sanasi: {contact_date}

🏆 OLDINGI YETKAZIB BERUVCHI (G'OLIB):
• Korxona: {prev_supplier}
{prev_supplier_line}

🔗 Xarid havolasi: {url}
"""

    deadline = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%dT19:00:00+05:00")

    result = _call_bx("tasks.task.add", {
        "fields": {
            "TITLE": f"🎯 [Qayta xarid] {customer[:80]} — {title[:80]}",
            "DESCRIPTION": description.strip(),
            "CREATED_BY": int(UMID_USER_ID),
            "RESPONSIBLE_ID": int(UMID_USER_ID),
            "DEADLINE": deadline,
            "PRIORITY": "2",
            "TAGS": ["QaytaXarid", "Tender", "Radar"],
        }
    })

    task_obj = result.get("result", {}).get("task", {})
    task_id = task_obj.get("id")
    if task_id:
        proc_id = str(lot.get("procedure_id") or "")
        mark_lot_as_sent(lot_key, proc_id, customer, title, str(task_id))
        return {
            "success": True,
            "task_id": task_id,
            "lot_key": lot_key,
            "task_url": f"https://softytest.bitrix24.uz/company/personal/user/{UMID_USER_ID}/tasks/task/view/{task_id}/"
        }
    return {"success": False, "error": result.get("error_description") or str(result)}


def send_multiple_radar_tasks(lots: list) -> dict:
    """Bir nechta lotlarni Bitrix24 ga vazifa qilib yuborish (dublikatlarni chetlab o'tadi)."""
    created = []
    skipped = []
    failed = []

    for lot in lots:
        lot_key = get_lot_key(lot)
        if is_lot_already_sent(lot_key):
            skipped.append((lot.get("customer") or "")[:40])
            continue

        res = create_radar_task(lot)
        if res.get("success"):
            created.append({
                "task_id": res["task_id"],
                "customer": (lot.get("customer") or lot.get("title") or "")[:60],
                "task_url": res["task_url"]
            })
        elif res.get("already_sent"):
            skipped.append((lot.get("customer") or "")[:40])
        else:
            failed.append({
                "customer": (lot.get("customer") or lot.get("title") or "")[:60],
                "error": res.get("error")
            })

    return {
        "success": True,
        "created_count": len(created),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "created": created,
        "skipped": skipped,
        "failed": failed
    }
