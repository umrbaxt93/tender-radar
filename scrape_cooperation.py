"""
Softy Platforma — cooperation.uz ni Mac'dan scrape qilib JSON'ga yozish.

cooperation.uz chet el/datacenter IP'larni bloklaydi — Hostinger serveri
(Germaniya) unga ulana olmaydi, lekin bu skript ishga tushadigan O'zbekiston
IP'sidan (Mac) ochiladi. Shuning uchun bu qism serverda EMAS, shu yerda
ishlaydi; natija keyin sync_cooperation.sh orqali serverga uzatiladi.

Ishga tushirish: python3 scrape_cooperation.py [chiqish_fayli.json]
"""
import json
import logging
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import app.adapters.cooperation as C  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "exports" / "cooperation_latest.json"
OUT.parent.mkdir(parents=True, exist_ok=True)


def main():
    a = C.CooperationAdapter()
    all_rows = []
    for plan_type, label in C.PLAN_TYPES:
        prev = None
        for page in range(1, 200):
            try:
                rows = a._parse_rows(a._fetch(f"/plans/{plan_type}?page={page}"))
            except Exception as ex:
                print(f"  {plan_type} sahifa {page}: xato ({ex}) — shu turni to'xtatamiz", file=sys.stderr)
                break
            if not rows:
                break
            mapped = [a._map(plan_type, label, c) for c in rows]
            ids = tuple(m["id"] for m in mapped)
            if ids == prev:
                break
            prev = ids
            all_rows.extend(mapped)
        print(f"  {plan_type}: tugadi, jami {len(all_rows)}", file=sys.stderr)

    uniq = {r["id"]: r for r in all_rows}
    OUT.write_text(json.dumps(list(uniq.values()), ensure_ascii=False), encoding="utf-8")
    print(f"✅ {len(uniq)} ta noyob reja -> {OUT} ({OUT.stat().st_size:,} bayt)", file=sys.stderr)


if __name__ == "__main__":
    main()
