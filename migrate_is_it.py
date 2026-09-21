"""
Softy Platforma — `lots.is_it` ustunini qo'shish (bir martalik migratsiya).

Bu ustun IT toifasini OLDINDAN hisoblab saqlaydi, shuning uchun qidiruv/filtr
har so'rovda 40+ kalit so'zni butun bazada qayta tekshirmaydi — shunchaki
`WHERE is_it = 1` (indekslangan, tezkor).

Qiymatlar: NULL = hali tasniflanmagan, 1 = IT, 0 = IT emas.
Xavfsiz qayta ishga tushiriladi — ustun allaqachon bo'lsa, hech narsa qilmaydi.
"""
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "softy_procurement.db"


def main():
    conn = sqlite3.connect(str(DB))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(lots)").fetchall()]
    if "is_it" in cols:
        print("is_it ustuni allaqachon mavjud — o'tkazib yuborildi.", file=sys.stderr)
    else:
        conn.execute("ALTER TABLE lots ADD COLUMN is_it INTEGER;")
        print("✅ is_it ustuni qo'shildi.", file=sys.stderr)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_lots_is_it ON lots(is_it);")
    conn.commit()
    print("✅ indeks tayyor.", file=sys.stderr)

    unclassified = conn.execute("SELECT COUNT(*) FROM lots WHERE is_it IS NULL").fetchone()[0]
    print(f"tasniflanmagan qator: {unclassified}", file=sys.stderr)


if __name__ == "__main__":
    main()
