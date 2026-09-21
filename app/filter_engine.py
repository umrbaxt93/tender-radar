"""
Softy Platforma — Filter Engine (17.E)
14 ta filtr parametri, 'Qaysi sana bo'yicha?' tanlovi,
tezkor davrlar (Asia/Tashkent) va butun baza bo'yicha server-side qidiruv.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional, Set
from app.search_engine import parse_search_query, get_query_variations, highlight_text

# Ruxsat etilgan sana maydonlari
ALLOWED_DATE_FIELDS = {
    "announcement_date": "E’lon berilgan sana",
    "deadline_date": "Taklif topshirishning oxirgi sanasi",
    "result_date": "Natija e’lon qilingan sana",
    "contract_date": "Shartnoma imzolangan sana",
    "delivery_date": "Yetkazib berish sanasi",
    "license_end_date": "Litsenziya tugash sanasi",
    "support_end_date": "Texnik yordam tugash sanasi",
    "created_in_db_date": "Bazaga qo‘shilgan sana"
}

def resolve_quick_date_range(quick_period: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Tezkor davrlar: shu oy, o‘tgan oy, shu yil, o‘tgan yil, oxirgi 12 oy
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    if quick_period == "this_month":
        start = now.replace(day=1).strftime("%Y-%m-%d")
        return start, today_str
    elif quick_period == "last_month":
        first_this_month = now.replace(day=1)
        last_month_end = first_this_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start.strftime("%Y-%m-%d"), last_month_end.strftime("%Y-%m-%d")
    elif quick_period == "this_year":
        start = now.replace(month=1, day=1).strftime("%Y-%m-%d")
        return start, today_str
    elif quick_period == "last_year":
        last_year = now.year - 1
        return f"{last_year}-01-01", f"{last_year}-12-31"
    elif quick_period == "last_12_months":
        start = (now - timedelta(days=365)).strftime("%Y-%m-%d")
        return start, today_str

    return None, None

def build_search_filter_query(
    view_mode: str = "lots", # 'lots', 'companies', 'contracts'
    query_str: Optional[str] = None,
    platforms: Optional[List[str]] = None,
    procurement_type: Optional[str] = None,
    official_status: Optional[str] = None,
    brand: Optional[str] = None,
    product_family: Optional[str] = None,
    buyer_inn_or_name: Optional[str] = None,
    supplier_inn_or_name: Optional[str] = None,
    region: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    has_contract: Optional[bool] = None,
    expiry_known: Optional[bool] = None,
    verification_status: Optional[str] = None,
    assigned_staff_id: Optional[str] = None,
    crm_status: Optional[str] = None,
    date_field: str = "announcement_date",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    quick_period: Optional[str] = None,
    include_missing_dates: bool = False,
    sort_by: str = "announcement_date",
    sort_desc: bool = True,
    it_only: Optional[bool] = None,
    limit: Optional[int] = 50,
    offset: int = 0
) -> Tuple[str, List[Any], Set[str]]:
    """
    SQL so'rovini va parametrlarini dinamik shakllantirish.
    """
    conditions = []
    params = []
    query_words: Set[str] = set()

    # 1. Matnli qidiruv (Search Query)
    if query_str and query_str.strip():
        parsed = parse_search_query(query_str)
        q_tokens = parsed["normal_keywords"] + parsed["exact_phrases"]
        all_vars = set()
        for tok in q_tokens:
            vars_for_tok = get_query_variations(tok)
            all_vars.update(vars_for_tok)
            query_words.update(vars_for_tok)

        # FTS yoki LIKE orqali qidirish
        if all_vars:
            sub_clauses = []
            for v in all_vars:
                clean_v = f"%{v}%"
                sub_clauses.append("""(
                    l.title LIKE ? OR l.description LIKE ? OR l.buyer_name LIKE ? 
                    OR l.buyer_inn LIKE ? OR l.supplier_name LIKE ? OR l.winner_name LIKE ?
                    OR l.contract_number LIKE ? OR l.extracted_text LIKE ?
                    OR EXISTS (SELECT 1 FROM contract_items ci WHERE ci.lot_id = l.id AND (ci.product_name LIKE ? OR ci.brand LIKE ? OR ci.product_family LIKE ?))
                )""")
                params.extend([clean_v] * 11)

            conditions.append(f"({' OR '.join(sub_clauses)})")

        # Exclusions (-word)
        for exc in parsed["excluded_words"]:
            clean_exc = f"%{exc}%"
            conditions.append("""(
                l.title NOT LIKE ? AND l.description NOT LIKE ? AND l.buyer_name NOT LIKE ?
            )""")
            params.extend([clean_exc] * 3)

    # 2. Platformalar filtri
    if platforms:
        placeholders = ",".join(["?"] * len(platforms))
        conditions.append(f"l.platform_id IN ({placeholders})")
        params.extend(platforms)

    # 3. Xarid turi
    if procurement_type:
        conditions.append("l.procurement_type = ?")
        params.append(procurement_type)

    # 4. Rasmiy holati
    if official_status:
        conditions.append("l.official_status = ?")
        params.append(official_status)

    # 5. Brend va Mahsulot oilasi
    if brand:
        conditions.append("EXISTS (SELECT 1 FROM contract_items ci WHERE ci.lot_id = l.id AND LOWER(ci.brand) = LOWER(?))")
        params.append(brand)
    if product_family:
        conditions.append("EXISTS (SELECT 1 FROM contract_items ci WHERE ci.lot_id = l.id AND LOWER(ci.product_family) = LOWER(?))")
        params.append(product_family)

    # 6. Buyurtmachi / Yetkazib beruvchi
    if buyer_inn_or_name:
        clean_buyer = f"%{buyer_inn_or_name}%"
        conditions.append("(l.buyer_inn LIKE ? OR l.buyer_name LIKE ?)")
        params.extend([clean_buyer, clean_buyer])

    if supplier_inn_or_name:
        clean_sup = f"%{supplier_inn_or_name}%"
        conditions.append("(l.supplier_inn LIKE ? OR l.supplier_name LIKE ? OR l.winner_name LIKE ?)")
        params.extend([clean_sup, clean_sup, clean_sup])

    # 7. Hudud
    if region:
        conditions.append("(l.region LIKE ? OR c.region LIKE ?)")
        params.extend([f"%{region}%", f"%{region}%"])

    # 8. Summa oralig'i
    if min_price is not None:
        conditions.append("l.final_price >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("l.final_price <= ?")
        params.append(max_price)

    # 9. Shartnomasi mavjudligi
    if has_contract is True:
        conditions.append("(l.has_contract = 1 OR l.contract_url IS NOT NULL OR l.contract_number IS NOT NULL)")
    elif has_contract is False:
        conditions.append("(l.has_contract = 0 AND l.contract_url IS NULL AND l.contract_number IS NULL)")

    # 9b. IT toifasi (oldindan hisoblangan l.is_it ustuniga qarab — tezkor,
    # har so'rovda kalit so'zlarni qayta tekshirmaydi)
    if it_only:
        conditions.append("l.is_it = 1")

    # 10. Tugash sanasi ma'lum/noma'lum
    if expiry_known is True:
        conditions.append("l.license_end_date IS NOT NULL AND l.license_end_date != ''")
    elif expiry_known is False:
        conditions.append("(l.license_end_date IS NULL OR l.license_end_date = '')")

    # 11. Tekshirish holati
    if verification_status:
        conditions.append("l.verification_status = ?")
        params.append(verification_status)

    # 12. Mas'ul xodim
    if assigned_staff_id:
        conditions.append("c.assigned_staff_id = ?")
        params.append(assigned_staff_id)

    # 13. CRM holati
    if crm_status:
        conditions.append("c.crm_status = ?")
        params.append(crm_status)

    # 14. Sana filtri ("Qaysi sana bo'yicha?")
    actual_date_field = date_field if date_field in ALLOWED_DATE_FIELDS else "announcement_date"

    # Tezkor davr tekshiruvi
    if quick_period and quick_period != "custom":
        q_start, q_end = resolve_quick_date_range(quick_period)
        if q_start and q_end:
            date_from = q_start
            date_to = q_end

    date_conditions = []
    if date_from:
        date_conditions.append(f"l.{actual_date_field} >= ?")
        params.append(date_from)
    if date_to:
        date_conditions.append(f"l.{actual_date_field} <= ?")
        params.append(date_to)

    if date_conditions:
        if include_missing_dates:
            conditions.append(f"(({' AND '.join(date_conditions)}) OR l.{actual_date_field} IS NULL OR l.{actual_date_field} = '')")
        else:
            conditions.append(f"({' AND '.join(date_conditions)} AND l.{actual_date_field} IS NOT NULL AND l.{actual_date_field} != '')")

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Sort order
    sort_dir = "DESC" if sort_desc else "ASC"
    order_col = f"l.{sort_by}" if sort_by in ALLOWED_DATE_FIELDS or sort_by in ["final_price", "start_price"] else "l.announcement_date"

    # limit=None -> LIMIT/OFFSET qatori umuman qo'shilmaydi (faqat COUNT(*) uchun
    # ishlatiladi). Avval bu joyda limit=100000 qattiq yozilgan edi va COUNT(*)
    # shu 100000ga cheklangan quyi so'rov ustidan hisoblanardi — natijada
    # 100 000dan katta baza uchun total_count doim noto'g'ri, kichraytirilgan
    # holda qaytardi (120k+ yozuv borida ham 100000 deb ko'rsatardi).
    limit_clause = f"LIMIT {int(limit)} OFFSET {int(offset)}" if limit is not None else ""

    if view_mode == "lots":
        sql = f"""
        SELECT 
            l.*,
            c.phone as buyer_phone,
            c.email as buyer_email,
            c.legal_address as buyer_address,
            c.assigned_staff_name,
            c.crm_status,
            s.name as platform_name,
            (
                SELECT json_group_array(
                    json_object(
                        'id', ci.id,
                        'product_name', ci.product_name,
                        'brand', ci.brand,
                        'product_family', ci.product_family,
                        'quantity', ci.quantity,
                        'unit', ci.unit,
                        'unit_price', ci.unit_price,
                        'total_price', ci.total_price,
                        'is_purchased_product', ci.is_purchased_product
                    )
                )
                FROM contract_items ci WHERE ci.lot_id = l.id
            ) as items_json
        FROM lots l
        LEFT JOIN companies c ON l.buyer_inn = c.inn
        LEFT JOIN sources s ON l.platform_id = s.id
        {where_clause}
        ORDER BY {order_col} {sort_dir}
        {limit_clause};
        """
    elif view_mode == "companies":
        sql = f"""
        SELECT 
            c.inn,
            c.name,
            c.phone,
            c.email,
            c.legal_address,
            c.region,
            c.proof_status,
            c.assigned_staff_id,
            c.assigned_staff_name,
            c.crm_status,
            c.next_task_text,
            c.next_task_date,
            MIN(l.announcement_date) as first_purchase_date,
            MAX(l.announcement_date) as latest_purchase_date,
            COUNT(DISTINCT l.id) as distinct_lots_count,
            COUNT(DISTINCT CASE WHEN l.has_contract = 1 THEN l.id END) as verified_contracts_count,
            GROUP_CONCAT(DISTINCT l.supplier_name) as suppliers_list,
            MIN(CASE WHEN l.license_end_date >= DATE('now') THEN l.license_end_date END) as nearest_license_expiry
        FROM companies c
        JOIN lots l ON l.buyer_inn = c.inn
        LEFT JOIN sources s ON l.platform_id = s.id
        {where_clause}
        GROUP BY c.inn
        ORDER BY latest_purchase_date DESC
        {limit_clause};
        """
    else: # 'contracts'
        sql = f"""
        SELECT 
            l.id as lot_id,
            l.lot_number,
            l.contract_number,
            l.contract_url,
            l.contract_date,
            l.license_end_date,
            l.final_price as contract_amount,
            l.currency,
            l.buyer_inn,
            l.buyer_name,
            l.supplier_name,
            l.platform_id,
            s.name as platform_name,
            ci.id as item_id,
            ci.product_name,
            ci.brand,
            ci.product_family,
            ci.quantity,
            ci.unit,
            ci.unit_price,
            ci.total_price,
            ci.is_purchased_product
        FROM lots l
        JOIN contract_items ci ON ci.lot_id = l.id
        LEFT JOIN companies c ON l.buyer_inn = c.inn
        LEFT JOIN sources s ON l.platform_id = s.id
        {where_clause}
        ORDER BY l.contract_date DESC
        {limit_clause};
        """

    return sql, params, query_words

def execute_search(filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Qidiruv va filtrlarni bajarish, highlighting qo'llash,
    umumiy hisob-kitoblarni va statistikani chiqarish.
    """
    import json
    from app.database import db_session

    view_mode = filters.get("view_mode", "lots")
    limit = int(filters.get("limit", 50))
    offset = int(filters.get("offset", 0))

    q_input = filters.get("query") or filters.get("query_str") or filters.get("keyword") or filters.get("q")
    sql, params, query_words = build_search_filter_query(
        view_mode=view_mode,
        query_str=q_input,
        platforms=filters.get("platforms"),
        procurement_type=filters.get("procurement_type"),
        official_status=filters.get("official_status"),
        brand=filters.get("brand"),
        product_family=filters.get("product_family"),
        buyer_inn_or_name=filters.get("buyer"),
        supplier_inn_or_name=filters.get("supplier"),
        region=filters.get("region"),
        min_price=filters.get("min_price"),
        max_price=filters.get("max_price"),
        has_contract=filters.get("has_contract"),
        expiry_known=filters.get("expiry_known"),
        verification_status=filters.get("verification_status"),
        assigned_staff_id=filters.get("assigned_staff_id"),
        crm_status=filters.get("crm_status"),
        date_field=filters.get("date_field", "announcement_date"),
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
        quick_period=filters.get("quick_period"),
        include_missing_dates=filters.get("include_missing_dates", False),
        sort_by=filters.get("sort_by", "announcement_date"),
        sort_desc=filters.get("sort_desc", True),
        it_only=filters.get("it_only"),
        limit=limit,
        offset=offset
    )

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        raw_rows = [dict(r) for r in cursor.fetchall()]

        # Count query
        # To get the count accurately without limit/offset:
        sql_no_limit, params_no_limit, _ = build_search_filter_query(
            view_mode=view_mode,
            query_str=q_input,
            platforms=filters.get("platforms"),
            procurement_type=filters.get("procurement_type"),
            official_status=filters.get("official_status"),
            brand=filters.get("brand"),
            product_family=filters.get("product_family"),
            buyer_inn_or_name=filters.get("buyer"),
            supplier_inn_or_name=filters.get("supplier"),
            region=filters.get("region"),
            min_price=filters.get("min_price"),
            max_price=filters.get("max_price"),
            has_contract=filters.get("has_contract"),
            expiry_known=filters.get("expiry_known"),
            verification_status=filters.get("verification_status"),
            assigned_staff_id=filters.get("assigned_staff_id"),
            crm_status=filters.get("crm_status"),
            date_field=filters.get("date_field", "announcement_date"),
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
            quick_period=filters.get("quick_period"),
            include_missing_dates=filters.get("include_missing_dates", False),
            sort_by=filters.get("sort_by", "announcement_date"),
            sort_desc=filters.get("sort_desc", True),
            it_only=filters.get("it_only"),
            limit=None,
            offset=0
        )
        
        # Build count query directly
        clean_subquery = sql_no_limit.strip().rstrip(";")
        count_sql = f"SELECT COUNT(*) FROM ({clean_subquery}) as sub;"
        cursor.execute(count_sql, params_no_limit)
        total_count = cursor.fetchone()[0]

        # Process highlighting and items
        processed_items = []
        total_amount = 0.0
        unique_buyers = set()
        contracts_count = 0

        for row in raw_rows:
            if "items_json" in row and row["items_json"]:
                row["items"] = json.loads(row["items_json"])
            elif "items_json" in row:
                row["items"] = []

            # Highlighting and Match Reason (17.D)
            match_tags = []
            if query_words:
                title_hl, matched_title = highlight_text(row.get("title", ""), query_words)
                row["highlighted_title"] = title_hl if matched_title else row.get("title", "")
                
                desc_hl, matched_desc = highlight_text(row.get("description", ""), query_words)
                row["highlighted_description"] = desc_hl

                # Check items for "Xarid mahsuloti sifatida aniqlandi"
                item_matched = False
                for it in row.get("items", []):
                    p_name = it.get("product_name", "")
                    p_hl, matched_p = highlight_text(p_name, query_words)
                    if matched_p:
                        item_matched = True
                        it["highlighted_name"] = p_hl

                if item_matched:
                    match_tags.append({"type": "PRODUCT_MATCH", "label": "Xarid mahsuloti sifatida aniqlandi", "badge_class": "badge-success"})
                elif matched_title or matched_desc:
                    match_tags.append({"type": "TEXT_MATCH", "label": "Matnda uchradi", "badge_class": "badge-info"})
            else:
                row["highlighted_title"] = row.get("title", "")
                row["highlighted_description"] = row.get("description", "")

            row["match_tags"] = match_tags

            # Accumulate stats
            price = row.get("final_price") or row.get("contract_amount") or 0.0
            total_amount += float(price)
            if row.get("buyer_inn"):
                unique_buyers.add(row["buyer_inn"])
            if row.get("has_contract") or row.get("contract_number"):
                contracts_count += 1

            processed_items.append(row)

    return {
        "view_mode": view_mode,
        "total_count": total_count,
        "items": processed_items,
        "limit": limit,
        "offset": offset,
        "query_words": list(query_words),
        "stats": {
            "total_records": total_count,
            "total_amount": total_amount,
            "unique_buyers_count": len(unique_buyers),
            "contracts_count": contracts_count
        }
    }

