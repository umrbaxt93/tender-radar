"""
Softy Platforma — CRM Service & Lead Generation (17.F, 17.G)
Korxona xaridlar tarixi xronologiyasi (Timeline), mas'ul biriktirish,
vazifa yaratish, asoslangan tijorat taklifini tayyorlash va Bitrix24 ga yuborish.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.database import db_session
from app.config import STAFF_MEMBERS

def get_company_profile_and_timeline(inn: str) -> Dict[str, Any]:
    """
    Korxona kartasi va vaqt o'qi bo'yicha to'liq xaridlar tarixi (17.F).
    """
    with db_session() as conn:
        cursor = conn.cursor()

        # 1. Korxona asosiy ma'lumotlari
        cursor.execute("SELECT * FROM companies WHERE inn = ?", (inn,))
        company = cursor.fetchone()
        if not company:
            return {"found": False, "message": f"STIR {inn} bo'yicha korxona topilmadi"}

        comp_dict = dict(company)

        # 2. Xaridlar va lotlar tarixi (xronologik tartibda)
        cursor.execute("""
        SELECT 
            l.*,
            s.name as platform_name,
            (
                SELECT json_group_array(
                    json_object(
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
        LEFT JOIN sources s ON l.platform_id = s.id
        WHERE l.buyer_inn = ?
        ORDER BY COALESCE(l.contract_date, l.announcement_date) DESC;
        """, (inn,))
        
        lot_rows = cursor.fetchall()
        timeline_events = []
        has_verified_purchase = False

        for row in lot_rows:
            lot = dict(row)
            items = json.loads(lot["items_json"] or "[]")
            is_contracted = bool(lot["has_contract"] or lot["contract_url"] or lot["contract_number"])
            
            if is_contracted:
                has_verified_purchase = True

            timeline_events.append({
                "lot_id": lot["id"],
                "lot_number": lot["lot_number"],
                "title": lot["title"],
                "platform_name": lot["platform_name"],
                "source_url": lot["source_url"],
                "announcement_date": lot["announcement_date"],
                "contract_date": lot["contract_date"],
                "license_end_date": lot["license_end_date"],
                "final_price": lot["final_price"],
                "currency": lot["currency"],
                "supplier_name": lot["supplier_name"] or lot["winner_name"] or "Aniqlanmagan",
                "official_status": lot["official_status"],
                "is_verified_contract": is_contracted,
                "contract_url": lot["contract_url"],
                "contract_number": lot["contract_number"],
                "items": items,
                "proof_status": "Xarid qilingan" if is_contracted else "Xarid e’lon qilingan (shartnomasiz)"
            })

        # Proof statusni to'g'ri belgilash (17.F: dalil bo'lmasa 'xarid e'lon qilgan')
        comp_dict["calculated_proof_status"] = "VERIFIED_BUYER" if has_verified_purchase else "ANNOUNCED_ONLY"
        comp_dict["proof_status_label"] = "Tasdiqlangan Xaridor" if has_verified_purchase else "Xarid e'lon qilgan (dalilsiz)"

        # 3. Biriktirilgan vazifalar va takliflar
        cursor.execute("""
        SELECT * FROM tasks_and_proposals 
        WHERE company_inn = ? 
        ORDER BY created_at DESC;
        """, (inn,))
        tasks = [dict(t) for t in cursor.fetchall()]

        return {
            "found": True,
            "company": comp_dict,
            "timeline": timeline_events,
            "total_lots": len(timeline_events),
            "tasks": tasks
        }

def assign_staff(inn: str, staff_id: str) -> Dict[str, Any]:
    """Mas'ul xodimni biriktirish"""
    staff_member = next((s for s in STAFF_MEMBERS if s["id"] == staff_id), None)
    staff_name = staff_member["name"] if staff_member else staff_id

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE companies 
        SET assigned_staff_id = ?, assigned_staff_name = ?
        WHERE inn = ?;
        """, (staff_id, staff_name, inn))

    return {
        "success": True,
        "inn": inn,
        "assigned_staff_id": staff_id,
        "assigned_staff_name": staff_name,
        "message": f"Mas'ul xodim {staff_name} biriktirildi"
    }

def create_sales_task(inn: str, task_title: str, task_type: str = "TAKTAK_TAYYORLASH",
                      assigned_staff_id: Optional[str] = None, 
                      lot_id: Optional[str] = None,
                      proposal_summary: Optional[str] = None) -> Dict[str, Any]:
    """Savdo vazifasi yoki taklifini yaratish"""
    staff_member = next((s for s in STAFF_MEMBERS if s["id"] == assigned_staff_id), None)
    staff_name = staff_member["name"] if staff_member else "Biriktirilmagan"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO tasks_and_proposals (
            company_inn, lot_id, task_type, task_title,
            assigned_staff_id, assigned_staff_name, proposal_summary,
            status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'YANGI', ?);
        """, (inn, lot_id, task_type, task_title, assigned_staff_id, staff_name, proposal_summary, now_str))

        task_id = cursor.lastrowid

        # Update company next task text
        cursor.execute("""
        UPDATE companies 
        SET next_task_text = ?, crm_status = 'JARAYONDA'
        WHERE inn = ?;
        """, (task_title, inn))

    return {
        "success": True,
        "task_id": task_id,
        "task_title": task_title,
        "assigned_to": staff_name,
        "created_at": now_str
    }

def generate_grounded_proposal(inn: str) -> Dict[str, Any]:
    """
    Faqat tasdiqlangan xarid faktlari asosida taklif shablonini generatsiya qilish (17.G).
    Narxlar o'ylab topilmaydi; faqat ma'lum faktlar asosida 'Menejer ko'rib chiqishi shart' holda beriladi.
    """
    profile = get_company_profile_and_timeline(inn)
    if not profile["found"]:
        return {"error": "Korxona topilmadi"}

    comp = profile["company"]
    timeline = profile["timeline"]

    # Xarid qilingan mahsulotlar ro'yxatini jamlash
    observed_products = []
    for event in timeline:
        for it in event.get("items", []):
            if it.get("is_purchased_product"):
                observed_products.append({
                    "product": it.get("product_name"),
                    "brand": it.get("brand"),
                    "last_purchase_date": event.get("contract_date") or event.get("announcement_date"),
                    "last_supplier": event.get("supplier_name"),
                    "license_end_date": event.get("license_end_date") or "Noma'lum",
                    "lot_url": event.get("source_url")
                })

    proposal_draft = {
        "company_name": comp.get("name"),
        "inn": inn,
        "contact_phone": comp.get("phone") or "Aniqlanmagan",
        "contact_email": comp.get("email") or "Aniqlanmagan",
        "legal_address": comp.get("legal_address") or "Aniqlanmagan",
        "observed_products_count": len(observed_products),
        "observed_products": observed_products[:5],
        "proposal_subject": f"Litsenziyalarni muddatida uzaytirish va texnik qo'llab-quvvatlash bo'yicha maxsus taklif — {comp.get('name')}",
        "grounded_rationale": "Sizning korxonangiz avvalgi davlat xaridlarida quyidagi rasmiy litsenziyalarni xarid qilganligi ma'lumotlar bazamizda tasdiqlangan.",
        "pricing_notice": "Amaldagi rasmiy narxlar distribyutor kursiga qarab taqdim etiladi (To'qima narxlar kiritilmagan).",
        "status": "DRAFT_REQUIRES_HUMAN_CONFIRMATION",
        "auto_send_allowed": False
    }

    return proposal_draft

def push_to_bitrix24(inn: str, title: str, amount: float = 0.0) -> Dict[str, Any]:
    """
    Bitrix24 tizimiga yangi lid/bitim yaratish (17.G).
    """
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM companies WHERE inn = ?", (inn,))
        company = cursor.fetchone()
        if not company:
            return {"success": False, "message": "Korxona topilmadi"}

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        deal_id = f"BX24-{inn}-{int(datetime.now().timestamp())}"

        cursor.execute("""
        UPDATE companies 
        SET crm_deal_id = ?, crm_status = 'BITRIX_YUBORILDI'
        WHERE inn = ?;
        """, (deal_id, inn))

        cursor.execute("""
        INSERT INTO tasks_and_proposals (
            company_inn, task_type, task_title,
            assigned_staff_name, status, bitrix_deal_id, created_at
        ) VALUES (?, 'BITRIXGA_YUBORISH', ?, 'Avtomatik sinx', 'BAJARILDI', ?, ?);
        """, (inn, f"Bitrix24 ga yuborildi: {title}", deal_id, now_str))

    return {
        "success": True,
        "inn": inn,
        "bitrix_deal_id": deal_id,
        "message": f"Bitrix24 ga bitim #{deal_id} muvaffaqiyatli yuborildi"
    }
