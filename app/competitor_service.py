"""
Softy Platforma — Competitor Intelligence Service
Barcha birja savdolarida ishtirok etgan korxonalarni INN (STIR) va nomi orqali qidirish,
IT va Umumiy (barcha sohalar) filtrlash, hamda o'ynalgan tashkilotlar va lotlar tahlili.
"""

import sqlite3
from typing import Dict, Any, List, Optional
from app.config import DB_PATH
from app.date_utils import calculate_accurate_end_date

IT_SEARCH_KEYWORDS = [
    "server", "litsenziya", "dastur", "kompyuter", "noutbuk",
    "printer", "tarmoq", "antivirus", "cctv", "kamera",
    "kartridj", "monitoring", "cloud", "telekom", "erp",
    "crm", "texnik", "internet", "proyektor", "1c",
    "modem", "router", "switch", "ssd", "hdd", "axborot", "informatika"
]


def search_competitors(
    query: str = "",
    mode: str = "it",
    limit: int = 50,
    page: int = 1
) -> Dict[str, Any]:
    """
    Raqobatchilarni qidirish:
    - mode == 'it': Faqat IT yo'nalishidagi lotlarda yutgan korxonalar
    - mode == 'all': Barcha birja savdolari (101k+ lot, 14k+ korxona)
    - query: STIR yoki korxona nomi
    """
    limit = min(max(int(limit), 10), 100)
    page = max(int(page), 1)
    offset = (page - 1) * limit

    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    where_clauses = ["supplier_inn IS NOT NULL AND supplier_inn != ''"]
    params: List[Any] = []

    if mode == "it":
        it_clause = " OR ".join(["lower(title) LIKE ?" for _ in IT_SEARCH_KEYWORDS])
        where_clauses.append(f"({it_clause})")
        params.extend([f"%{kw}%" for kw in IT_SEARCH_KEYWORDS])

    if query and query.strip():
        q = query.strip()
        clean_q = q.replace('"', '').replace("'", "")
        where_clauses.append("(supplier_inn LIKE ? OR lower(supplier_name) LIKE ?)")
        params.extend([f"%{q}%", f"%{clean_q.lower()}%"])

    where_sql = " AND ".join(where_clauses)

    # Jami soni
    cursor.execute(f"SELECT COUNT(DISTINCT supplier_inn) FROM lots WHERE {where_sql}", params)
    total_count = cursor.fetchone()[0]

    # Saralangan ro'yxat
    sql = f"""
        SELECT 
            COALESCE(MAX(supplier_name), 'Noma''lum') as name,
            supplier_inn as stir,
            COUNT(*) as wins_count,
            SUM(COALESCE(final_price, contract_amount, 0)) as total_won,
            MAX(COALESCE(contract_date, announcement_date)) as last_win,
            COUNT(DISTINCT buyer_inn) as unique_buyers,
            ROUND(AVG(CASE WHEN start_price > 0 AND final_price > 0 AND start_price > final_price 
                           THEN ((start_price - final_price) * 100.0 / start_price) 
                           ELSE 8.5 END), 1) as avg_discount_pct
        FROM lots
        WHERE {where_sql}
        GROUP BY supplier_inn
        ORDER BY total_won DESC
        LIMIT ? OFFSET ?;
    """
    cursor.execute(sql, params + [limit, offset])
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "success": True,
        "mode": mode,
        "query": query,
        "total": total_count,
        "page": page,
        "pages": (total_count + limit - 1) // limit,
        "competitors": rows
    }


def get_competitor_deep_intel(q_inn_or_name: str) -> Dict[str, Any]:
    """
    Korxona qaysi tashkilotlar bilan lotda o'ynaganligi va barcha lotlari:
    1. O'ynalgan tashkilotlar ro'yxati (Buyurtmachilar va Yetkazib beruvchilar, summasi, lotlar soni, muddatlari)
    2. Barcha individual lotlar va ularning aniq tugash sanalari
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    q = (q_inn_or_name or "").strip()
    clean_q = q.replace('"', '').replace("'", "")

    if not q:
        conn.close()
        return {"success": False, "error": "STIR yoki korxona nomi kiritilmadi"}

    # 1. Supplier sifatida tekshirish (Yetkazib beruvchi / G'olib bo'lgan lotlar)
    cursor.execute("""
        SELECT 
            COALESCE(l.buyer_inn, 'Noma''lum') as org_inn,
            COALESCE(l.buyer_name, 'Noma''lum') as org_name,
            'Buyurtmachi (Mijoz)' as org_role,
            COUNT(*) as lot_count,
            SUM(COALESCE(l.final_price, l.contract_amount, 0)) as total_sum,
            MIN(COALESCE(l.contract_date, l.announcement_date)) as first_date,
            MAX(COALESCE(l.contract_date, l.announcement_date)) as last_date
        FROM lots l
        WHERE l.supplier_inn = ? OR lower(l.supplier_name) LIKE ?
        GROUP BY COALESCE(l.buyer_inn, l.buyer_name)
        ORDER BY total_sum DESC;
    """, (q, f"%{clean_q.lower()}%"))
    supplier_orgs = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT 
            l.id, l.lot_number, l.title, l.lot_category,
            l.buyer_name, l.buyer_inn, l.platform_id,
            COALESCE(l.final_price, l.contract_amount, 0) as contract_amount,
            l.start_price, l.contract_date, l.license_end_date,
            l.supplier_name as winner_name, l.supplier_inn as winner_inn,
            l.has_contract, l.source_url, l.announcement_date,
            'supplier' as my_role
        FROM lots l
        WHERE l.supplier_inn = ? OR lower(l.supplier_name) LIKE ?
        ORDER BY COALESCE(l.contract_date, l.announcement_date) DESC
        LIMIT 500;
    """, (q, f"%{clean_q.lower()}%"))
    supplier_lots = [dict(r) for r in cursor.fetchall()]

    # 2. Buyer sifatida tekshirish (Buyurtmachi bo'lgan lotlar)
    cursor.execute("""
        SELECT 
            COALESCE(l.supplier_inn, 'Noma''lum') as org_inn,
            COALESCE(l.supplier_name, 'Noma''lum') as org_name,
            'Yetkazib beruvchi (G''olib)' as org_role,
            COUNT(*) as lot_count,
            SUM(COALESCE(l.final_price, l.contract_amount, 0)) as total_sum,
            MIN(COALESCE(l.contract_date, l.announcement_date)) as first_date,
            MAX(COALESCE(l.contract_date, l.announcement_date)) as last_date
        FROM lots l
        WHERE l.buyer_inn = ? OR lower(l.buyer_name) LIKE ?
        GROUP BY COALESCE(l.supplier_inn, l.supplier_name)
        ORDER BY total_sum DESC;
    """, (q, f"%{clean_q.lower()}%"))
    buyer_orgs = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT 
            l.id, l.lot_number, l.title, l.lot_category,
            l.buyer_name, l.buyer_inn, l.platform_id,
            COALESCE(l.final_price, l.contract_amount, 0) as contract_amount,
            l.start_price, l.contract_date, l.license_end_date,
            l.supplier_name as winner_name, l.supplier_inn as winner_inn,
            l.has_contract, l.source_url, l.announcement_date,
            'buyer' as my_role
        FROM lots l
        WHERE l.buyer_inn = ? OR lower(l.buyer_name) LIKE ?
        ORDER BY COALESCE(l.contract_date, l.announcement_date) DESC
        LIMIT 500;
    """, (q, f"%{clean_q.lower()}%"))
    buyer_lots = [dict(r) for r in cursor.fetchall()]

    # Kombinatsiya qilish: Agar supplier sifatida ko'proq bo'lsa yoki buyer sifatida
    if len(supplier_lots) >= len(buyer_lots):
        all_lots = supplier_lots + buyer_lots[:(500 - len(supplier_lots))]
        all_orgs = supplier_orgs + [o for o in buyer_orgs if o["org_inn"] not in [so["org_inn"] for so in supplier_orgs]]
        primary_role = "supplier"
        primary_label = "Yetkazib beruvchi / G'olib"
    else:
        all_lots = buyer_lots + supplier_lots[:(500 - len(buyer_lots))]
        all_orgs = buyer_orgs + [o for o in supplier_orgs if o["org_inn"] not in [bo["org_inn"] for bo in buyer_orgs]]
        primary_role = "buyer"
        primary_label = "Buyurtmachi Tashkilot"

    # Har bir lot uchun aniq tugash sanasini hisoblash
    for l in all_lots:
        c_date = l.get("contract_date")
        l_end = l.get("license_end_date")
        title = l.get("title", "")
        cat = l.get("lot_category", "")
        l["contract_end_date"] = calculate_accurate_end_date(title, c_date, l_end, cat)

    # Korxona nomi va haqiqiy STIRini aniqlash
    comp_name = q
    actual_stir = q
    if supplier_lots:
        comp_name = supplier_lots[0].get("winner_name") or q
        actual_stir = supplier_lots[0].get("winner_inn") or q
    elif buyer_lots:
        comp_name = buyer_lots[0].get("buyer_name") or q
        actual_stir = buyer_lots[0].get("buyer_inn") or q
    else:
        cursor.execute("SELECT name FROM companies WHERE inn = ?", (q,))
        c = cursor.fetchone()
        if c: comp_name = c[0]

    conn.close()

    total_amount = sum(float(l.get("contract_amount", 0) or 0) for l in all_lots)

    return {
        "success": True,
        "company": {
            "inn": actual_stir,
            "name": comp_name,
            "role": primary_role,
            "role_label": primary_label,
            "total_lots": len(all_lots),
            "total_amount": total_amount,
            "unique_organizations": len(all_orgs),
            "supplier_lots_count": len(supplier_lots),
            "buyer_lots_count": len(buyer_lots)
        },
        "organizations_played": all_orgs,
        "supplier_organizations": supplier_orgs,
        "buyer_organizations": buyer_orgs,
        "lots": all_lots,
        "total": len(all_lots)
    }
