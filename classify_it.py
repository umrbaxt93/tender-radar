"""
Softy Platforma — `lots.is_it` ni to'ldirish (idempotent, qayta ishga tushirilishi mumkin).

Har ishga tushirilganda FAQAT hali tasniflanmagan (is_it IS NULL) qatorlarni
oladi va tasniflaydi — shuning uchun kundalik cron'ga qo'shib qo'yish xavfsiz:
yangi kelgan lotlar avtomatik ravishda IT/IT-emas deb belgilanadi.

Ishga tushirish: python3 classify_it.py [bo'lak_hajmi]
"""
import sys
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from app.full_it_seeder import is_it_software  # noqa: E402

DB = BASE / "data" / "softy_procurement.db"
BATCH = int(sys.argv[1]) if len(sys.argv) > 1 else 50000


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, description FROM lots WHERE is_it IS NULL LIMIT ?", (BATCH,)
    ).fetchall()

    if not rows:
        print("tasniflanadigan yangi qator yo'q.", file=sys.stderr)
        return

    it_ids, non_it_ids = [], []
    for r in rows:
        text = f"{r['title'] or ''} {r['description'] or ''}"
        (it_ids if is_it_software(text) else non_it_ids).append(r["id"])

    cur = conn.cursor()
    for chunk_start in range(0, len(it_ids), 500):
        chunk = it_ids[chunk_start:chunk_start + 500]
        cur.execute(f"UPDATE lots SET is_it=1 WHERE id IN ({','.join('?'*len(chunk))})", chunk)
    for chunk_start in range(0, len(non_it_ids), 500):
        chunk = non_it_ids[chunk_start:chunk_start + 500]
        cur.execute(f"UPDATE lots SET is_it=0 WHERE id IN ({','.join('?'*len(chunk))})", chunk)
    conn.commit()

    remaining = conn.execute("SELECT COUNT(*) FROM lots WHERE is_it IS NULL").fetchone()[0]
    print(f"tasniflandi: {len(rows)} (+{len(it_ids)} IT, +{len(non_it_ids)} IT emas)  qolgan: {remaining}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
