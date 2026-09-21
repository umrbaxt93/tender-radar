"""
Softy Platforma — Dashboard ma'lumotlarini jonli bazadan qayta hisoblash.

Bu skript umid/index.html ichiga qotib yozilgan barcha statik ma'lumotlarni
(sarlavha raqamlari, Radar imkoniyatlari, Eksport jadvali, Top mijozlar,
Raqobatchilar) joriy `lots` jadvalidan qayta hisoblaydi va bitta JSON faylga
yozadi. Natijani HTML ga joylashtirish uchun apply_dashboard_data.py ishlatiladi.

Ishga tushirish: /opt/alt/python311/bin/python3 generate_dashboard_data.py
Natija: data/dashboard_data.json
"""
import json
import re
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from app.full_it_seeder import IT_KEYWORDS, is_it_software, detect_brand_and_family  # noqa: E402
from app.date_utils import calculate_accurate_end_date  # noqa: E402


# calculate_accurate_end_date's qoida-3 (aniq muddat topilmasa) 30 kunlik
# "yetkazib berish" muddatini qaytaradi — bu jismoniy tovar uchun to'g'ri,
# lekin Radar buni "litsenziya tugash sanasi" deb noto'g'ri o'qib qolardi:
# yaqinda import qilingan har qanday IT lot (aniq muddat so'zisiz) darhol
# "tez orada qayta xarid kerak" deb belgilanardi. Radar uchun FAQAT haqiqiy
# litsenziya/obuna muddati signali bo'lgan xaridlar hisobga olinadi — shu
# signal topilmasa, qatorning o'zi RADAR_ITEMS ga kiritilmaydi (RAW_EXPORT
# uchun esa calculate_accurate_end_date to'liq holicha ishlatiladi, chunki
# u yerda 30-kunlik yetkazib berish muddati semantik jihatdan to'g'ri).
_LICENSE_RE = re.compile(
    r'3\s*(yil|god|year|36\s*oy)|2\s*(yil|goda|year|24\s*oy)|'
    r'1\s*(yil|god|year|12\s*oy)|yillik|annual|6\s*oy|polgoda|half-year|'
    r'3\s*oy|kvartal', re.IGNORECASE)
_LICENSE_KEYWORDS = [
    "litsenziya", "licen", "dastur", "software", "antivirus", "kaspersky",
    "fortinet", "microsoft", "1c", "obuna", "subscri", "texnik xizmat",
    "texnik qo'llab", "monitoring", "eset", "autocad", "windows", "cloud",
]


def radar_renewal_date(text: str, contract_date: str):
    """Faqat aniq litsenziya/obuna muddati signali bo'lganda sana qaytaradi."""
    if not contract_date or len(str(contract_date)) < 10:
        return None
    t = (text or "").lower()
    if not (_LICENSE_RE.search(t) or any(k in t for k in _LICENSE_KEYWORDS)):
        return None
    return calculate_accurate_end_date(text, contract_date, None, "")

DB_PATH = BASE / "data" / "softy_procurement.db"
OUT_PATH = BASE / "data" / "dashboard_data.json"

TODAY = datetime.now().date()
RAW_EXPORT_CAP = 6000
RADAR_MIN_DAYS = -60   # shuncha kungacha o'tib ketgan bo'lsa ham hali "HOT"
RADAR_MAX_DAYS = 180   # bundan uzoqroq kutilayotgan yangilanish ko'rsatilmaydi


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Bazani o'qish
# ─────────────────────────────────────────────────────────────────────────────

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT id, lot_number, title, description, platform_id, official_status,
           announcement_date, start_price, final_price, contract_amount,
           currency, buyer_inn, buyer_name, supplier_inn, supplier_name,
           winner_name, region, source_url, contract_url
    FROM lots
""").fetchall()
log(f"jami lot o'qildi: {len(rows)}")

companies_count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
by_source = {r["platform_id"]: 0 for r in rows}
for r in rows:
    by_source[r["platform_id"]] = by_source.get(r["platform_id"], 0) + 1


def txt(r):
    return f"{r['title'] or ''} {r['description'] or ''}"


def award_amount(r):
    for v in (r["contract_amount"], r["final_price"], r["start_price"]):
        if v and float(v) > 0:
            return float(v)
    return 0.0


def start_amount(r):
    v = r["start_price"]
    return float(v) if v and float(v) > 0 else award_amount(r)


def winner_of(r):
    return (r["winner_name"] or r["supplier_name"] or "").strip()


it_rows = [r for r in rows if is_it_software(txt(r))]
log(f"IT deb tasniflangan lot: {len(it_rows)}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. RAW_EXPORT_ITEMS — IT bo'yicha g'olib/shartnoma ma'lumoti bor lotlar
# ─────────────────────────────────────────────────────────────────────────────

export_candidates = []
for r in it_rows:
    w = winner_of(r)
    amt = award_amount(r)
    if not w and amt <= 0:
        continue
    export_candidates.append(r)

export_candidates.sort(key=lambda r: r["announcement_date"] or "", reverse=True)
export_candidates = export_candidates[:RAW_EXPORT_CAP]

RAW_EXPORT_ITEMS = []
for r in export_candidates:
    deal_sum = award_amount(r)
    RAW_EXPORT_ITEMS.append({
        "customer_name": r["buyer_name"] or "",
        "customer_inn": r["buyer_inn"] or "",
        "product_name": (r["title"] or "")[:600],
        "contract_date": r["announcement_date"] or "",
        "contract_end_date": calculate_accurate_end_date(
            r["title"] or "", r["announcement_date"], None, "") or "",
        "start_sum": start_amount(r),
        "deal_sum": deal_sum,
        "winner_name": winner_of(r),
        "winner_inn": r["supplier_inn"] or "",
        "lot_url": r["source_url"] or r["contract_url"] or "",
        "source": r["platform_id"],
        "lot_id": r["id"],
    })
log(f"RAW_EXPORT_ITEMS: {len(RAW_EXPORT_ITEMS)} (jami nomzod {len(export_candidates)})")


# ─────────────────────────────────────────────────────────────────────────────
# 3. TOP_CUSTOMERS — barcha lotlar bo'yicha eng ko'p sarflagan xaridorlar
# ─────────────────────────────────────────────────────────────────────────────

cust = {}
for r in rows:
    inn = (r["buyer_inn"] or "").strip()
    if not inn:
        continue
    c = cust.setdefault(inn, {"name": None, "region": None, "proc_count": 0, "total_spend": 0.0})
    c["proc_count"] += 1
    c["total_spend"] += award_amount(r)
    if not c["name"] and r["buyer_name"]:
        c["name"] = r["buyer_name"]
    if not c["region"] and r["region"]:
        c["region"] = r["region"]

TOP_CUSTOMERS = sorted(
    ({"name": v["name"] or "Noma'lum", "stir": k, "proc_count": v["proc_count"],
      "total_spend": round(v["total_spend"], 2), "region": v["region"] or "O'zbekiston"}
     for k, v in cust.items()),
    key=lambda x: x["total_spend"], reverse=True
)[:24]
log(f"TOP_CUSTOMERS: {len(TOP_CUSTOMERS)}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Raqobatchilar (g'oliblar) — IT va umumiy
# ─────────────────────────────────────────────────────────────────────────────

def build_competitors(row_list, limit):
    agg = {}
    for r in row_list:
        w = winner_of(r)
        if not w:
            continue
        inn = (r["supplier_inn"] or "").strip()
        key = (w, inn)
        a = agg.setdefault(key, {"wins_count": 0, "total_won": 0.0, "last_win": "",
                                  "buyers": set(), "disc_sum": 0.0, "disc_n": 0})
        a["wins_count"] += 1
        a["total_won"] += award_amount(r)
        if (r["announcement_date"] or "") > a["last_win"]:
            a["last_win"] = r["announcement_date"] or ""
        if r["buyer_inn"]:
            a["buyers"].add(r["buyer_inn"])
        s, d = start_amount(r), award_amount(r)
        if s > 0 and 0 < d <= s:
            a["disc_sum"] += (s - d) / s * 100.0
            a["disc_n"] += 1

    out = []
    for (name, inn), a in agg.items():
        out.append({
            "name": name, "stir": inn,
            "wins_count": a["wins_count"],
            "total_won": round(a["total_won"], 2),
            "last_win": a["last_win"],
            "unique_buyers": len(a["buyers"]),
            "avg_discount_pct": round(a["disc_sum"] / a["disc_n"], 1) if a["disc_n"] else 0.0,
        })
    out.sort(key=lambda x: x["total_won"], reverse=True)
    return out[:limit]


IT_COMPETITORS = build_competitors(it_rows, 50)
ALL_COMPETITORS = build_competitors(rows, 60)
log(f"IT_COMPETITORS: {len(IT_COMPETITORS)}  ALL_COMPETITORS: {len(ALL_COMPETITORS)}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. RADAR_ITEMS — qayta xarid (renewal) imkoniyatlari
# ─────────────────────────────────────────────────────────────────────────────

def radar_category(text):
    t = text.lower()
    if any(k in t for k in ("kaspersky", "касперск", "eset", "nod32", "antivirus",
                             "антивирус", "endpoint detection", " edr")):
        return "Antivirus/EDR"
    if any(k in t for k in ("fortigate", "fortinet", "firewall", "check point", "palo alto", "utm")):
        return "Firewall"
    if "dlp" in t or "data loss" in t:
        return "DLP"
    if "google workspace" in t or "g suite" in t:
        return "Google Workspace"
    if "azure" in t or ("cloud" in t and "microsoft" not in t):
        return "Cloud"
    if any(k in t for k in ("microsoft", "office 365", "m365", "windows", "sql server")):
        return "Microsoft"
    if any(k in t for k in ("zoom", "webinar", "видеоконференц")):
        return "Collaboration"
    if any(k in t for k in ("vmware", "veeam", "server", "сервер")):
        return "Server"
    if any(k in t for k in ("security", "xavfsiz", "безопас", "kiberxavfsizlik")):
        return "Cybersecurity-Other"
    return "IT Xizmatlari"


def radar_score(days):
    if days <= 7:
        return 90
    if days <= 14:
        return 85
    if days <= 30:
        return 80
    if days <= 60:
        return 70
    if days <= 90:
        return 60
    if days <= 120:
        return 50
    return 40


DISCOUNT_BY_CATEGORY = {
    "Antivirus/EDR": 5.0, "Firewall": 4.5, "Microsoft": 4.0, "Cloud": 4.0,
    "Collaboration": 5.5, "Server": 3.5, "DLP": 5.0, "Google Workspace": 5.0,
    "Cybersecurity-Other": 5.0, "IT Xizmatlari": 5.0,
}


def generate_ai_advice(customer, stir, brand, category, title, amount, last_purchase,
                        expected_renewal, previous_supplier, contact_days_before):
    discount = DISCOUNT_BY_CATEGORY.get(category, 5.0)
    suggested_price = round(amount * (1 - discount / 100.0), 2)
    supplier_txt = previous_supplier or "boshqa yetkazib beruvchi"
    analysis = (
        f"{customer} ilgari {supplier_txt} orqali {amount:,.0f} UZS qiymatida "
        f"'{title}' xarid qilgan ({last_purchase}). Ushbu xarid toifasi bo'yicha "
        f"buyurtmachining amaldagi litsenziya/xizmat muddati {expected_renewal} sanasida "
        f"yakunlanadi, bu esa takroriy renewal (qayta xarid) imkonini beradi."
    ).replace(",", " ")
    competitor_weakness = (
        f"{supplier_txt} odatda chakana narxga 10-18% ustama bilan kiradi va litsenziya "
        f"muddati tugashidan oldin mijoz bilan proaktiv aloqa qilmaydi. Bu — erta murojaat "
        f"qilgan yetkazib beruvchi uchun ustunlik oynasi."
    )
    recommended_strategy = (
        f"1. Rasmiy hamkorlik dasturi imtiyozidan foydalanib, {discount:.1f}% arzonroq narx taklif qilish.\n"
        f"2. Litsenziya/xizmat muddati tugashidan {contact_days_before} kun oldin IT bo'lim bilan bog'lanish.\n"
        f"3. Bepul texnik audit va sozlash xizmatini qo'shib, qaror qabul qilishni tezlashtirish."
    )
    action_plan = [
        f"1. {contact_days_before} kun oldin: STIR {stir} bo'yicha mas'ul shaxsni aniqlash.",
        f"2. Tijoriy taklif: {discount:.1f}% chegirmali ({suggested_price:,.0f} UZS).".replace(",", " "),
        "3. Texnik topshiriqqa SOFTY spetsifikatsiyasini kiritish.",
        "4. Bitrix24 orqali eslatma: renewal sanasigacha muntazam monitoring.",
    ]
    commercial_pitch = (
        f"Hurmatli {customer} rahbariyati va IT mas'ullari!\n\n"
        f"\"SOFTY\" MCHJ korxonangizda foydalanilayotgan '{title}' tizimi bo'yicha qayta xarid "
        f"va xizmat ko'rsatish yuzasidan qulay tijoriy shartlarni taklif etadi.\n\n"
        f"Biz rasmiy hamkorlik asosida to'g'ridan-to'g'ri ishlab chiqaruvchi narxlarida "
        f"({suggested_price:,.0f} UZS dan boshlab), bepul sozlash va texnik kafolat bilan "
        f"xizmat ko'rsatishga tayyormiz.\n\n"
        f"Batafsil ma'lumot va spetsifikatsiya taqdim etish uchun ruxsat bergaysiz.\n"
        f"Hurmat bilan, SOFTY Savdo bo'limi."
    ).replace(",", " ")
    return {
        "engine": "SOFTY Procurement AI Advisor (Uzbekistan B2B Engine)",
        "analysis": analysis,
        "competitor_weakness": competitor_weakness,
        "recommended_strategy": recommended_strategy,
        "suggested_discount_percent": discount,
        "suggested_price": suggested_price,
        "optimal_contact_days_before": contact_days_before,
        "action_plan": action_plan,
        "commercial_pitch": commercial_pitch,
    }


# Buyurtmachi + brend bo'yicha guruhlash, har guruhdan eng oxirgi xaridni olish
groups = {}
for r in it_rows:
    inn = (r["buyer_inn"] or "").strip()
    if not inn:
        continue
    brand, family = detect_brand_and_family(txt(r))
    key = (inn, brand)
    prev = groups.get(key)
    if prev is None or (r["announcement_date"] or "") > (prev["announcement_date"] or ""):
        groups[key] = r

log(f"buyurtmachi+brend guruhlari: {len(groups)}")

radar_candidates = []
for (inn, brand), r in groups.items():
    if brand == "IT Integratsiya":
        # Bu — detect_brand_and_family() ning aniqlanmagan holatlar uchun
        # umumiy "hammasi bitta savat" belgisi. Bir xaridorning turli-tuman
        # mahsulotlarini bitta soxta "takroriy xarid" sifatida guruhlash
        # noto'g'ri signal beradi, shuning uchun Radar'ga kiritilmaydi.
        continue
    title = r["title"] or ""
    renewal = radar_renewal_date(txt(r), r["announcement_date"])
    if not renewal:
        continue
    try:
        renewal_date = datetime.strptime(renewal[:10], "%Y-%m-%d").date()
    except Exception:
        continue
    days = (renewal_date - TODAY).days
    if not (RADAR_MIN_DAYS <= days <= RADAR_MAX_DAYS):
        continue

    score = radar_score(days)
    contact_days_before = 30 if score >= 85 else (45 if score >= 60 else 60)
    contact_by = renewal_date - timedelta(days=contact_days_before)
    if contact_by < TODAY:
        contact_by = TODAY

    amount = award_amount(r)
    customer = r["buyer_name"] or "Noma'lum tashkilot"
    category = radar_category(txt(r))
    previous_supplier = winner_of(r)

    radar_candidates.append({
        "_sort_days": days,
        "customer": customer,
        "score": score,
        "contact_by": contact_by.strftime("%Y-%m-%d"),
        "category": category,
        "brand": brand,
        "amount": amount,
        "expected_renewal": renewal_date.strftime("%Y-%m-%d"),
        "last_purchase": (r["announcement_date"] or "")[:10],
        "stir": inn,
        "region": r["region"] or "O'zbekiston",
        "title": title[:600],
        "source_url": r["source_url"] or r["contract_url"] or "",
        "previous_supplier": previous_supplier,
        "ai_advice": generate_ai_advice(customer, inn, brand, category, title, amount,
                                        (r["announcement_date"] or "")[:10],
                                        renewal_date.strftime("%Y-%m-%d"),
                                        previous_supplier, contact_days_before),
    })

# Eng shoshilinch (kam kun qolgan) birinchi
radar_candidates.sort(key=lambda x: x["_sort_days"])
RADAR_ITEMS = []
for i, c in enumerate(radar_candidates, start=1):
    c = dict(c)
    del c["_sort_days"]
    c["procedure_id"] = i
    RADAR_ITEMS.append(c)

radar_hot = sum(1 for x in RADAR_ITEMS if x["score"] >= 80)
log(f"RADAR_ITEMS: {len(RADAR_ITEMS)}  (HOT: {radar_hot})")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Yakuniy natija
# ─────────────────────────────────────────────────────────────────────────────

source_line_parts = []
for pid, label in (("uzex", "UZEX"), ("ebirja", "E-Birja"), ("xt_xarid", "XT-Xarid"), ("cooperation", "Kooperatsiya")):
    n = by_source.get(pid, 0)
    if n:
        source_line_parts.append(f"{label}: {n:,}".replace(",", " "))

result = {
    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "header": {
        "total_lots": len(rows),
        "total_lots_fmt": f"{len(rows):,}".replace(",", " "),
        "source_breakdown": " | ".join(source_line_parts),
        "companies": companies_count,
        "companies_fmt": f"{companies_count:,}".replace(",", " "),
        "it_lots": len(it_rows),
        "it_lots_fmt": f"{len(it_rows):,}".replace(",", " "),
        "it_competitors": len(IT_COMPETITORS),
        "radar_total": len(RADAR_ITEMS),
        "radar_hot": radar_hot,
    },
    "RAW_EXPORT_ITEMS": RAW_EXPORT_ITEMS,
    "RADAR_ITEMS": RADAR_ITEMS,
    "TOP_CUSTOMERS": TOP_CUSTOMERS,
    "IT_COMPETITORS": IT_COMPETITORS,
    "ALL_COMPETITORS": ALL_COMPETITORS,
}

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False)

log(f"\n✅ Yozildi: {OUT_PATH}  ({OUT_PATH.stat().st_size:,} bayt)")
log(f"   jami lot={result['header']['total_lots']}  kompaniya={result['header']['companies']}  "
    f"IT={result['header']['it_lots']}  radar={result['header']['radar_total']} (HOT {radar_hot})  "
    f"eksport={len(RAW_EXPORT_ITEMS)}")
