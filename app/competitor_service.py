"""
Softy Platforma — Competitor Intelligence Service
Barcha birja savdolarida ishtirok etgan korxonalarni INN (STIR) va nomi orqali qidirish,
IT va Umumiy (barcha sohalar) filtrlash, hamda o'ynalgan tashkilotlar va lotlar tahlili.
"""

import sqlite3
from typing import Dict, Any, List, Optional
from app.config import DB_PATH
from app.date_utils import calculate_accurate_end_date

# G'oliblarni topish uchun ikkita maydon bor: `supplier_inn`/`supplier_name`
# (yangi manbalar — E-Birja, XT-Xarid) va `winner_name` (asosan UZEX, INN'siz,
# faqat matn). Bazaning yarmidan ko'pi (UZEX, 73k+ yozuv) faqat winner_name'ga
# ega — faqat supplier_inn'ga qaraladigan eski so'rov shu manbani BUTUNLAY
# tashlab ketardi (tekshirildi: haqiqiy 20+ g'alabasi bo'lgan kompaniya
# "3 ta g'alaba" deb ko'rsatilgan edi).
_WINNER_PRESENT = (
    "((supplier_inn IS NOT NULL AND supplier_inn != '') "
    " OR (supplier_name IS NOT NULL AND supplier_name != '') "
    " OR (winner_name IS NOT NULL AND winner_name != ''))"
)
# INN bo'lsa shu bo'yicha, bo'lmasa (asosan UZEX) nom bo'yicha guruhlash —
# aks holda INN'siz yozuvlar butunlay yo'qolib qolardi.
_GROUP_KEY = (
    "COALESCE(NULLIF(supplier_inn,''), "
    "'N:' || lower(COALESCE(NULLIF(supplier_name,''), winner_name)))"
)
_AMOUNT = "COALESCE(final_price, contract_amount, start_price, 0)"


def search_competitors(
    query: str = "",
    mode: str = "it",
    limit: int = 50,
    page: int = 1
) -> Dict[str, Any]:
    """
    Raqobatchilarni qidirish:
    - mode == 'it': Faqat IT yo'nalishidagi lotlarda yutgan korxonalar
      (lots.is_it — app/full_it_seeder.py bilan bir xil, oldindan hisoblangan
      tasnif; ilgari bu yerda alohida, sinovdan o'tmagan kalit so'zlar
      ro'yxati bor edi)
    - mode == 'all': Barcha birja savdolari
    - query: STIR yoki korxona nomi
    """
    limit = min(max(int(limit), 10), 100)
    page = max(int(page), 1)
    offset = (page - 1) * limit

    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    where_clauses = [_WINNER_PRESENT]
    params: List[Any] = []

    if mode == "it":
        where_clauses.append("is_it = 1")

    if query and query.strip():
        q = query.strip()
        clean_q = q.replace('"', '').replace("'", "")
        where_clauses.append(
            "(supplier_inn LIKE ? OR lower(supplier_name) LIKE ? OR lower(winner_name) LIKE ?)"
        )
        params.extend([f"%{q}%", f"%{clean_q.lower()}%", f"%{clean_q.lower()}%"])

    where_sql = " AND ".join(where_clauses)

    # Jami soni (noyob raqobatchi, guruhlash kaliti bo'yicha)
    cursor.execute(f"SELECT COUNT(DISTINCT {_GROUP_KEY}) FROM lots WHERE {where_sql}", params)
    total_count = cursor.fetchone()[0]

    # Saralangan ro'yxat. avg_discount_pct: haqiqiy start>final solishtirilgan
    # yozuvlar bo'yichagina hisoblanadi (SQL AVG NULL'larni o'zi e'tiborsiz
    # qoldiradi) — ilgari solishtirish imkonsiz bo'lgan holatda ham 8.5%
    # degan o'ylab topilgan son qo'yilardi, bu haqiqiy ma'lumot sifatida
    # ko'rsatilardi.
    sql = f"""
        SELECT
            COALESCE(NULLIF(MAX(supplier_name),''), MAX(winner_name), 'Noma''lum') as name,
            COALESCE(NULLIF(MAX(supplier_inn),''), '') as stir,
            COUNT(*) as wins_count,
            SUM({_AMOUNT}) as total_won,
            MAX(COALESCE(contract_date, announcement_date)) as last_win,
            COUNT(DISTINCT buyer_inn) as unique_buyers,
            ROUND(COALESCE(AVG(CASE WHEN start_price > 0 AND {_AMOUNT} > 0 AND start_price > {_AMOUNT}
                           THEN ((start_price - {_AMOUNT}) * 100.0 / start_price)
                           ELSE NULL END), 0), 1) as avg_discount_pct
        FROM lots
        WHERE {where_sql}
        GROUP BY {_GROUP_KEY}
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

    # `winner_name`ga ham qarash SHART: UZEX yozuvlarining aksariyatida
    # supplier_inn/supplier_name umuman yo'q, faqat winner_name (matn) bor —
    # busiz bu yozuvlar qidiruvda ko'rinmasdi.
    supplier_match = "(l.supplier_inn = ? OR lower(l.supplier_name) LIKE ? OR lower(l.winner_name) LIKE ?)"
    supplier_params = (q, f"%{clean_q.lower()}%", f"%{clean_q.lower()}%")

    # 1. Supplier sifatida tekshirish (Yetkazib beruvchi / G'olib bo'lgan lotlar)
    cursor.execute(f"""
        SELECT
            COALESCE(l.buyer_inn, 'Noma''lum') as org_inn,
            COALESCE(l.buyer_name, 'Noma''lum') as org_name,
            'Buyurtmachi (Mijoz)' as org_role,
            COUNT(*) as lot_count,
            SUM({_AMOUNT}) as total_sum,
            MIN(COALESCE(l.contract_date, l.announcement_date)) as first_date,
            MAX(COALESCE(l.contract_date, l.announcement_date)) as last_date
        FROM lots l
        WHERE {supplier_match}
        GROUP BY COALESCE(l.buyer_inn, l.buyer_name)
        ORDER BY total_sum DESC;
    """, supplier_params)
    supplier_orgs = [dict(r) for r in cursor.fetchall()]

    cursor.execute(f"""
        SELECT
            l.id, l.lot_number, l.title, l.lot_category,
            l.buyer_name, l.buyer_inn, l.platform_id,
            {_AMOUNT} as contract_amount,
            l.start_price, l.contract_date, l.license_end_date,
            COALESCE(NULLIF(l.supplier_name,''), l.winner_name) as winner_name,
            l.supplier_inn as winner_inn,
            l.has_contract, l.source_url, l.announcement_date,
            'supplier' as my_role
        FROM lots l
        WHERE {supplier_match}
        ORDER BY COALESCE(l.contract_date, l.announcement_date) DESC
        LIMIT 500;
    """, supplier_params)
    supplier_lots = [dict(r) for r in cursor.fetchall()]

    # 2. Buyer sifatida tekshirish (Buyurtmachi bo'lgan lotlar)
    cursor.execute(f"""
        SELECT
            COALESCE(NULLIF(l.supplier_inn,''), 'N:'||lower(COALESCE(NULLIF(l.supplier_name,''), l.winner_name))) as org_inn,
            COALESCE(NULLIF(l.supplier_name,''), l.winner_name, 'Noma''lum') as org_name,
            'Yetkazib beruvchi (G''olib)' as org_role,
            COUNT(*) as lot_count,
            SUM({_AMOUNT}) as total_sum,
            MIN(COALESCE(l.contract_date, l.announcement_date)) as first_date,
            MAX(COALESCE(l.contract_date, l.announcement_date)) as last_date
        FROM lots l
        WHERE l.buyer_inn = ? OR lower(l.buyer_name) LIKE ?
        GROUP BY org_inn
        ORDER BY total_sum DESC;
    """, (q, f"%{clean_q.lower()}%"))
    buyer_orgs = [dict(r) for r in cursor.fetchall()]

    cursor.execute(f"""
        SELECT
            l.id, l.lot_number, l.title, l.lot_category,
            l.buyer_name, l.buyer_inn, l.platform_id,
            {_AMOUNT} as contract_amount,
            l.start_price, l.contract_date, l.license_end_date,
            COALESCE(NULLIF(l.supplier_name,''), l.winner_name) as winner_name,
            l.supplier_inn as winner_inn,
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
