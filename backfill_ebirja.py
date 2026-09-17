"""E-Birja bir martalik katta boyitish.

Bazadagi 28 000+ qator INN va mahsulot nomisiz saqlangan, chunki ro'yxat
endpointi bu maydonlarni bermaydi. Bu skript detal endpointi orqali ularni
to'ldiradi. Uzilib qolsa, qayta ishga tushirish xavfsiz: har safar faqat
hali to'ldirilmagan qatorlarni oladi.
"""
import logging, sys, time
logging.disable(logging.CRITICAL)
import app.adapters.ebirja as E
from app.database import db_session

batch = int(sys.argv[1]) if len(sys.argv) > 1 else 500
rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 100

def remaining():
    with db_session() as c:
        return c.execute("SELECT COUNT(*) n FROM lots WHERE platform_id='ebirja' "
                         "AND (buyer_inn IS NULL OR buyer_inn='')").fetchone()["n"]

a = E.EbirjaAdapter()
start = remaining()
print("to'ldirilmagan (boshida): %d" % start, flush=True)

total = 0
for i in range(rounds):
    left = remaining()
    if left == 0:
        print("✅ hammasi to'ldirildi", flush=True)
        break
    t0 = time.time()
    done = a.enrich_existing(limit=batch)
    total += done
    print("  bosqich %-3d +%-4d  jami %-6d  qoldi %-6d  (%.0fs)"
          % (i + 1, done, total, left - done, time.time() - t0), flush=True)
    if done == 0:
        print("  (yangi yozuv to'ldirilmadi — to'xtatildi)", flush=True)
        break

with db_session() as c:
    c.execute("UPDATE sources SET records_count=(SELECT COUNT(*) FROM lots WHERE lots.platform_id=sources.id)")
print("YAKUN: %d ta to'ldirildi, %d ta qoldi" % (total, remaining()), flush=True)
