"""
Softy Platforma — cooperation.uz JSON'ini jonli bazaga yuklash (SERVERDA ishlaydi).

Bu skript serverga DOIMIY joylashtiriladi (sync_cooperation.sh har safar shu
skriptni chaqiradi, o'zini qayta yubormaydi). Manbaga ulanmaydi — faqat
Mac'dan kelgan tayyor JSON faylni o'qib, INSERT OR IGNORE bilan bazaga
kiritadi (idempotent, dublikat yaratmaydi — id'lar hash asosida barqaror).

Ishga tushirish: python3 load_coop_remote.py <json_fayl_yoli>
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "softy_procurement.db"

if len(sys.argv) < 2:
    print("Foydalanish: python3 load_coop_remote.py <json_fayl>", file=sys.stderr)
    sys.exit(1)

json_path = Path(sys.argv[1])
rows = json.loads(json_path.read_text(encoding="utf-8"))

c = sqlite3.connect(str(DB))
c.execute("PRAGMA foreign_keys = ON;")
cur = c.cursor()

cols = ["id", "lot_number", "title", "description", "platform_id", "source_url",
        "procurement_type", "official_status", "announcement_date", "start_price",
        "currency", "buyer_inn", "buyer_name", "region", "extracted_text", "raw_data_json"]
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
sql = f"INSERT OR IGNORE INTO lots ({','.join(cols)}, created_in_db_date) VALUES ({','.join('?'*len(cols))}, ?)"

before = cur.execute("SELECT COUNT(*) FROM lots WHERE platform_id='cooperation'").fetchone()[0]
added = 0
for r in rows:
    cur.execute(sql, [r.get(k) for k in cols] + [now])
    added += cur.rowcount

cur.execute("UPDATE sources SET records_count=(SELECT COUNT(*) FROM lots WHERE lots.platform_id=sources.id) WHERE id='cooperation'")
cur.execute("UPDATE sources SET health_status='OK', last_successful_sync=? WHERE id='cooperation'", (now,))
c.commit()

after = cur.execute("SELECT COUNT(*) FROM lots WHERE platform_id='cooperation'").fetchone()[0]
print(f"cooperation: {before} -> {after} (+{added} yangi), JSON'da {len(rows)} ta")
