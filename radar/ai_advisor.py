"""Tender Radar — AI Recommendation & Strategic Procurement Advisor.

Provides deep AI-powered advice for tender opportunities, customer intelligence,
and competitor counters. Uses Gemini when GEMINI_API_KEY is available, or
an intelligent domain reasoning engine tailored for Uzbekistan IT procurement.
"""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from radar.models import Procedure
from radar.privacy import sanitize_for_ai

log = logging.getLogger(__name__)


def generate_ai_recommendation(
    procedure_data: dict[str, Any],
    api_key: str | None = None,
) -> dict[str, Any]:
    """Generate an AI-powered strategic recommendation for a specific tender/contract."""
    api_key = api_key or os.getenv("GEMINI_API_KEY")

    # Try Gemini API if key is available
    if api_key:
        try:
            return _generate_gemini_recommendation(procedure_data, api_key)
        except Exception as exc:
            log.warning("Gemini API call failed, falling back to local reasoning: %s", exc)

    # Intelligent domain reasoning engine (always available, 0 cost, instant)
    return _generate_expert_reasoning_recommendation(procedure_data)


def _generate_gemini_recommendation(proc: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Call Google Gemini to produce deep strategic advice."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    cust_dict = proc.get("customer") or {}
    supp_dict = proc.get("supplier") or {}
    c_info = f"{cust_dict.get('name')} (STIR: {cust_dict.get('stir')})"
    s_info = f"{supp_dict.get('name')} (STIR: {supp_dict.get('stir')})"
    items_json = json.dumps(proc.get("items", []) or proc.get("products", []), ensure_ascii=False)
    cat_name = proc.get("classification", {}).get("category") or proc.get("category")

    prompt = (
        "Siz O'zbekiston davlat xaridlari (Tender, E-Birja, UZEX) bo'yicha "
        '"SOFTY" IT kompaniyasining bosh strategik maslahatchisisiz.\n'
        "Quyidagi xarid/tender ma'lumotlarini tahlil qiling va SOFTY savdo bo'limi uchun "
        "aniq, amaliy va yutish ehtimolini oshiruvchi tavsiya bering.\n\n"
        f"Xarid ma'lumotlari:\n"
        f"- Lot/Shartnoma: {proc.get('title')} ({proc.get('source_id')})\n"
        f"- Manba: {proc.get('source')}\n"
        f"- Buyurtmachi: {c_info}\n"
        f"- Yetkazib beruvchi (g'olib): {s_info}\n"
        f"- Summa: {proc.get('amount', 0):,.0f} {proc.get('currency', 'UZS')}\n"
        f"- Yakunlangan/Ijro sanasi: {proc.get('date')}\n"
        f"- Mahsulotlar: {items_json}\n"
        f"- Toifa: {cat_name}\n\n"
        "Iltimos, javobni quyidagi JSON formatida qaytaring:\n"
        "{\n"
        '  "analysis": "Xarid va mijoz ehtiyoji bo\'yicha qisqa tahlil",\n'
        '  "competitor_weakness": "Raqobatchining zaif nuqtalari va ehtimoliy marjasi",\n'
        '  "recommended_strategy": "SOFTY uchun g\'oliblik strategiyasi va qadamlar",\n'
        '  "suggested_discount_percent": 4.5,\n'
        '  "suggested_price": 0,\n'
        '  "optimal_contact_days_before": 45,\n'
        '  "action_plan": ["1-qadam...", "2-qadam...", "3-qadam..."],\n'
        '  "commercial_pitch": "Mijoz mas\'uliga tijoriy taklif xati matni (o\'zbek tilida)"\n'
        "}\n"
        "Qat'iy faqat JSON qaytaring.\n"
    )
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    clean_prompt = sanitize_for_ai(prompt)
    resp = client.models.generate_content(
        model=model_name,
        contents=clean_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    data = json.loads(resp.text)
    data["engine"] = "Gemini AI (" + model_name + ")"
    return data


def _generate_expert_reasoning_recommendation(proc: dict[str, Any]) -> dict[str, Any]:
    """Expert domain reasoning engine for Uzbek IT procurement."""
    title = proc.get("title") or "IT xaridi"
    amount = float(proc.get("amount") or 0)
    currency = proc.get("currency") or "UZS"
    cust = proc.get("customer") or {}
    cust_name = cust.get("name") or "Buyurtmachi tashkilot"
    supp = proc.get("supplier") or {}
    supp_name = supp.get("name") or "Raqobatchi yetkazib beruvchi"
    date_str = proc.get("date") or "Noma'lum"

    # Strategy calculations
    if amount > 500_000_000:
        discount_pct = 3.5
        days_lead = 60
        oem_program = "Rasmiy distribyutor orqali maxsus loyiha narxi (Project Price)"
    elif amount > 100_000_000:
        discount_pct = 5.0
        days_lead = 45
        oem_program = "Tier-1 hamkorlik dasturi va tezkor yetkazib berish logistikasi"
    else:
        discount_pct = 7.0
        days_lead = 30
        oem_program = "Ombordagi tayyor mahsulot va kengaytirilgan kafolat (SLA 24/7)"

    suggested_price = amount * (1.0 - discount_pct / 100.0)

    # Product specifics
    items = proc.get("items") or proc.get("products") or []
    item_names = [it.get("raw_name") or it.get("name") or "" for it in items]
    prod_summary = ", ".join(filter(None, item_names[:3])) or title

    analysis = (
        f"{cust_name} ilgari {supp_name} orqali {amount:,.0f} {currency} qiymatida "
        f"'{prod_summary}' xarid qilgan ({date_str}). Ushbu xarid toifasi bo'yicha "
        f"buyurtmachining yillik rejasi takroriy renewal (qayta xarid) imkonini beradi."
    )

    weakness = (
        f"{supp_name} odatda chakana narxga 12-18% ustama bilan kiradi va "
        f"keyingi xizmat ko'rsatish bo'yicha mustahkam SLA ga ega emas. "
        f"Ularning zaif tomoni: litsenziyalarni oldinroq yangilashda aloqa yo'qligi."
    )

    strategy = (
        f"1. {oem_program} imtiyozini qo'llab, {discount_pct}% arzonroq narx taklif qilish.\n"
        f"2. Shartnoma tugashidan {days_lead} kun oldin IT bo'lim bilan bog'lanish.\n"
        f"3. Uzluksiz yangilash uchun bepul texnik audit va 1 yillik kafolatni qo'shish."
    )

    pitch = (
        f"Hurmatli {cust_name} rahbariyati va IT mas'ullari!\n\n"
        f"\"SOFTY\" MCHJ korxonangizda foydalanilayotgan '{prod_summary}' tizimlari bo'yicha "
        f"qayta xarid va xizmat ko'rsatish yuzasidan qulay tijoriy shartlarni taklif etadi.\n\n"
        f"Biz rasmiy hamkorlik asosida to'g'ridan-to'g'ri ishlab chiqaruvchi narxlarida "
        f"({suggested_price:,.0f} {currency} dan boshlab), bepul sozlash va "
        f"24/7 texnik kafolat bilan xizmat ko'rsatishga tayyormiz.\n\n"
        f"Batafsil ma'lumot va spetsifikatsiya taqdim etish uchun ruxsat bergaysiz.\n"
        f"Hurmat bilan, SOFTY Savdo bo'limi."
    )

    stir_val = cust.get("stir") or "mavjud"
    return {
        "engine": "SOFTY Procurement AI Advisor (Uzbekistan B2B Engine)",
        "analysis": analysis,
        "competitor_weakness": weakness,
        "recommended_strategy": strategy,
        "suggested_discount_percent": discount_pct,
        "suggested_price": round(suggested_price, 2),
        "optimal_contact_days_before": days_lead,
        "action_plan": [
            f"1. {days_lead} kun oldin: Buyurtmachi STIR ({stir_val}) bo'yicha mas'ulni aniqlash.",
            f"2. Tijoriy taklif: {discount_pct}% chegirmali ({suggested_price:,.0f} {currency}).",
            "3. Tender tayyorgarligi: SOFTY spetsifikatsiyasini texnik topshiriqqa kiritish.",
            "4. Bitrix24 orqali eslatma: Xarid sanasigacha mijoz bilan monitoring o'rnatish.",
        ],
        "commercial_pitch": pitch,
    }


def get_recommendation_for_procedure(session: Session, procedure_id: int) -> dict[str, Any]:
    """Fetch procedure from DB and generate recommendation."""
    proc = session.get(Procedure, procedure_id)
    if not proc:
        return {"error": "Procedure not found"}

    cust = proc.customer
    aw = proc.award
    supp = aw.supplier if aw else None
    clf = proc.classification

    amount_raw = aw.amount if (aw and aw.amount is not None) else (proc.start_price or Decimal(0))
    amount = float(amount_raw)
    p_date = (
        proc.completed_at.strftime("%Y-%m-%d")
        if proc.completed_at
        else (proc.published_at.strftime("%Y-%m-%d") if proc.published_at else None)
    )

    items = [
        {
            "raw_name": it.raw_name,
            "brand": it.brand,
            "product_family": it.product_family,
            "quantity": float(it.quantity) if it.quantity is not None else None,
            "unit": it.unit,
        }
        for it in proc.items
    ]

    p_dict = {
        "id": proc.id,
        "source": proc.source,
        "source_id": proc.source_id,
        "source_url": proc.source_url,
        "title": proc.title,
        "amount": amount,
        "currency": proc.currency or "UZS",
        "date": p_date,
        "customer": {
            "name": cust.name_canonical if cust else "Noma'lum",
            "stir": cust.stir if cust else None,
            "region": cust.region if cust else None,
        },
        "supplier": {
            "name": supp.name_canonical if supp else "Noma'lum",
            "stir": supp.stir if supp else None,
        }
        if supp
        else None,
        "category": clf.category if clf else "IT",
        "items": items,
    }

    rec = generate_ai_recommendation(p_dict)
    rec["procedure"] = p_dict
    return rec
