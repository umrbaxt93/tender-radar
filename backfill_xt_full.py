"""XT-Xarid to'liq tarixiy backfill — 3 reestrni oxirigacha varaqlaydi.

online_shop reestri ro'yxatning o'zida to'liq ma'lumot beradi (INN + mahsulot
nomi), shuning uchun detal so'rovi shart emas — tez. selection/tender ro'yxati
mahsulot nomisiz (title=contract_name), lekin INN va summa bilan — kenglik uchun.

Kursor (data/xt_backfill.cursor) bilan: uzilsa o'sha joydan davom etadi.
INSERT OR IGNORE — dublikat bo'lmaydi.
"""
import os, sys, logging
logging.disable(logging.CRITICAL)
import app.adapters.xt_xarid as X
from app.database import db_session

REGISTRIES = [
    ("online_shop_contract_public_registry", {"nad": False, "is_comm_shop": False}),
    ("contract_public_registry", {"proc_type": "selection"}),
    ("contract_public_registry", {"proc_type": "tender"}),
]
PAGE = 100
BASE = os.path.dirname(os.path.abspath(__file__))
CURSOR = os.path.join(BASE, "data", "xt_backfill.cursor")
DONE = os.path.join(BASE, "data", "xt_backfill.done")

max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 400

if os.path.exists(DONE):
    print("XT backfill allaqachon tugagan"); sys.exit(0)

reg_i, offset = 0, 0
try:
    with open(CURSOR) as f:
        reg_i, offset = map(int, f.read().split())
except Exception:
    pass

def count():
    with db_session() as c:
        return c.execute("SELECT COUNT(*) FROM lots WHERE platform_id='xt_xarid'").fetchone()[0]

a = X.XtXaridAdapter()
start = count()
print("xt_xarid boshida: %d  (reg %d, offset %d dan)" % (start, reg_i, offset), flush=True)

inserted = pages = 0
while pages < max_pages and reg_i < len(REGISTRIES):
    reg, filt = REGISTRIES[reg_i]
    try:
        batch = a._rpc("contract_ref", {"ref": reg, "op": "read",
                                        "limit": PAGE, "offset": offset, "filters": filt})
    except Exception as ex:
        # HTTP 400 = reestrning offset chegarasiga yetdik (bu reestr shuncha
        # chuqur varaqlashga ruxsat bermaydi). To'xtash o'rniga keyingi reestrga
        # o'tamiz — aks holda shu offsetda cheksiz qotardik.
        print("  reg %d off %d xato (%s) — keyingi reestrga o'tamiz" % (reg_i, offset, str(ex)[:40]), flush=True)
        reg_i += 1; offset = 0
        with open(CURSOR, "w") as f: f.write("%d %d" % (reg_i, offset))
        continue
    if not isinstance(batch, list) or not batch:
        # reestr tugadi → keyingisiga o'tamiz
        print("  reg %d tugadi (offset %d)" % (reg_i, offset), flush=True)
        reg_i += 1; offset = 0
        with open(CURSOR, "w") as f: f.write("%d %d" % (reg_i, offset))
        continue
    rows = [a._map_contract(c) for c in batch if c.get("number")]
    inserted += a._insert(rows)
    offset += PAGE; pages += 1
    with open(CURSOR, "w") as f: f.write("%d %d" % (reg_i, offset))
    if pages % 20 == 0:
        print("  ...%d sahifa, +%d, hozir %d ta" % (pages, inserted, count()), flush=True)

with db_session() as c:
    c.execute("UPDATE sources SET records_count=(SELECT COUNT(*) FROM lots WHERE lots.platform_id=sources.id)")

if reg_i >= len(REGISTRIES):
    with open(DONE, "w") as f: f.write("done")
    print("✅ XT BACKFILL TUGADI — jami %d ta (+%d bu run)" % (count(), count() - start), flush=True)
else:
    print("davom etadi: reg %d offset %d, hozir %d ta (+%d)" % (reg_i, offset, count(), count() - start), flush=True)
