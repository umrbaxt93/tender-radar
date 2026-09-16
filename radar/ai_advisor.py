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

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from radar.models import (
    Award,
    Classification,
    Organization,
    Procedure,
    RenewalOpportunity,
)
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


def compute_macro_metrics(session: Session) -> dict[str, Any]:
    """Compute aggregate business and market metrics from the tender database."""
    total_procs = session.scalar(select(func.count(Procedure.id))) or 0
    it_procs = session.scalar(
        select(func.count(Classification.procedure_id)).where(Classification.is_it.is_(True))
    ) or 0
    total_volume = float(session.scalar(select(func.sum(Procedure.start_price))) or 0)
    it_volume = float(
        session.scalar(
            select(func.sum(Procedure.start_price))
            .join(Classification, Classification.procedure_id == Procedure.id)
            .where(Classification.is_it.is_(True))
        )
        or 0
    )

    # Top IT Categories
    cat_rows = session.execute(
        select(Classification.category, func.count(Classification.procedure_id).label("cnt"))
        .where(Classification.is_it.is_(True), Classification.category.is_not(None))
        .group_by(Classification.category)
        .order_by(desc("cnt"))
        .limit(6)
    ).all()
    top_categories = [{"category": r[0], "count": r[1]} for r in cat_rows]

    # Top IT Brands
    brand_rows = session.execute(
        select(Classification.brand, func.count(Classification.procedure_id).label("cnt"))
        .where(Classification.is_it.is_(True), Classification.brand.is_not(None))
        .group_by(Classification.brand)
        .order_by(desc("cnt"))
        .limit(8)
    ).all()
    top_brands = [{"brand": r[0], "count": r[1]} for r in brand_rows]

    # Top Purchasing Organizations (Buyers) in IT
    buyer_rows = session.execute(
        select(
            Organization.name_canonical,
            Organization.stir,
            Organization.region,
            func.count(Procedure.id).label("lots_count"),
            func.sum(Procedure.start_price).label("total_budget"),
        )
        .join(Procedure, Procedure.customer_org_id == Organization.id)
        .join(Classification, Classification.procedure_id == Procedure.id)
        .where(Classification.is_it.is_(True))
        .group_by(
            Organization.id,
            Organization.name_canonical,
            Organization.stir,
            Organization.region,
        )
        .order_by(desc("total_budget"))
        .limit(8)
    ).all()
    top_buyers = [
        {
            "name": r[0],
            "stir": r[1],
            "region": r[2],
            "lots_count": r[3],
            "total_budget": float(r[4] or 0),
        }
        for r in buyer_rows
    ]

    # Top Winning Competitors / Suppliers
    supp_rows = session.execute(
        select(
            Organization.name_canonical,
            Organization.stir,
            func.count(Award.procedure_id).label("wins_count"),
            func.sum(Award.amount).label("total_awarded"),
        )
        .join(Award, Award.supplier_org_id == Organization.id)
        .join(Procedure, Procedure.id == Award.procedure_id)
        .join(Classification, Classification.procedure_id == Procedure.id)
        .where(Classification.is_it.is_(True))
        .group_by(Organization.id, Organization.name_canonical, Organization.stir)
        .order_by(desc("total_awarded"))
        .limit(8)
    ).all()
    top_competitors = [
        {
            "name": r[0],
            "stir": r[1],
            "wins_count": r[2],
            "total_awarded": float(r[3] or 0),
        }
        for r in supp_rows
    ]

    # Renewal pipeline
    total_renewals = session.scalar(select(func.count(RenewalOpportunity.id))) or 0
    hot_renewals = session.scalar(
        select(func.count(RenewalOpportunity.id)).where(RenewalOpportunity.score >= 80)
    ) or 0

    renewal_rows = session.execute(
        select(
            RenewalOpportunity.id,
            RenewalOpportunity.score,
            RenewalOpportunity.contact_by_at,
            RenewalOpportunity.expected_renewal_at,
            Procedure.id.label("proc_id"),
            Procedure.title,
            Procedure.start_price,
            Organization.name_canonical.label("customer_name"),
            Classification.category,
            Classification.brand,
        )
        .join(Procedure, Procedure.id == RenewalOpportunity.procedure_id)
        .outerjoin(Organization, Organization.id == Procedure.customer_org_id)
        .outerjoin(Classification, Classification.procedure_id == Procedure.id)
        .order_by(desc(RenewalOpportunity.score))
        .limit(10)
    ).all()

    top_pipeline = [
        {
            "id": r[0],
            "score": r[1],
            "contact_by": r[2].strftime("%Y-%m-%d") if r[2] else None,
            "expected_date": r[3].strftime("%Y-%m-%d") if r[3] else None,
            "procedure_id": r[4],
            "title": r[5],
            "budget": float(r[6] or 0),
            "customer": r[7] or "Noma'lum",
            "category": r[8] or "IT",
            "brand": r[9] or "-",
        }
        for r in renewal_rows
    ]

    return {
        "total_procedures": total_procs,
        "it_procedures": it_procs,
        "it_share_pct": round((it_procs / total_procs * 100) if total_procs else 0, 1),
        "total_volume_uzs": total_volume,
        "it_volume_uzs": it_volume,
        "top_categories": top_categories,
        "top_brands": top_brands,
        "top_buyers": top_buyers,
        "top_competitors": top_competitors,
        "total_renewals": total_renewals,
        "hot_renewals": hot_renewals,
        "top_pipeline": top_pipeline,
    }


def generate_macro_business_strategy(
    session: Session,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Generate overall business and market intelligence report for Softy LLC."""
    metrics = compute_macro_metrics(session)
    api_key = api_key or os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            strategy = _generate_gemini_macro_strategy(metrics, api_key)
            strategy["metrics"] = metrics
            return strategy
        except Exception as exc:
            log.warning("Gemini macro strategy failed, falling back to expert reasoning: %s", exc)

    strategy = _generate_expert_macro_strategy(metrics)
    strategy["metrics"] = metrics
    return strategy


def _generate_gemini_macro_strategy(metrics: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Call Google Gemini to generate high-level executive strategic advice for Softy LLC."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    prompt = (
        "Siz O'zbekiston davlat xaridlari (UZEX, E-Birja, XT-Xarid) bo'yicha "
        "\"SOFTY LLC\" IT kompaniyasi bosh strategik maslahatchisisiz.\n"
        "Quyidagi real bozor ma'lumotlari asosida Softy rahbariyati uchun "
        "makro biznes strategiyasi va savdo yo'l xaritasini tayyorlang:\n\n"
        f"Statistika:\n"
        f"- Jami tahlil qilingan lotlar: {metrics['total_procedures']} ta\n"
        f"- IT lotlar ulushi: {metrics['it_procedures']} ta ({metrics['it_share_pct']}%)\n"
        f"- IT bozor hajmi: {metrics['it_volume_uzs']:,.0f} UZS\n"
        f"- Top IT brendlar: {json.dumps(metrics['top_brands'], ensure_ascii=False)}\n"
        f"- Top xaridorlar: {json.dumps(metrics['top_buyers'], ensure_ascii=False)}\n"
        f"- Top raqobatchilar: {json.dumps(metrics['top_competitors'], ensure_ascii=False)}\n"
        f"- Renewal imkoniyatlari: {metrics['total_renewals']} ta "
        f"(HOT: {metrics['hot_renewals']} ta)\n\n"
        "Quyidagi JSON formatda professional, aniq va amaliy tavsiya bering:\n"
        "{\n"
        '  "executive_summary": "Bozor holati va Softy imkoniyatlari haqida 3-4 gap",\n'
        '  "target_segments": ["Segment 1...", "Segment 2..."],\n'
        '  "competitor_counter_strategy": "Raqobatchilarni yutish bo\'yicha aniq taktika",\n'
        '  "pricing_and_discount_policy": "Tavsiya etiladigan chegirma va marja diapazoni",\n'
        '  "renewal_attack_plan": "Litsenziyalar bo\'yicha mijozlarga chiqish tartibi",\n'
        '  "actionable_milestones": ["1-qadam...", "2-qadam...", "3-qadam...", "4-qadam..."]\n'
        "}\n"
        "Qat'iy faqat JSON qaytaring.\n"
    )

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
    data["engine"] = f"Gemini AI ({model_name})"
    return data


def _generate_expert_macro_strategy(metrics: dict[str, Any]) -> dict[str, Any]:
    """Domain reasoning business strategy for Uzbekistan B2B IT procurement."""
    it_vol_billions = metrics["it_volume_uzs"] / 1_000_000_000
    top_buyers = metrics.get("top_buyers", [])
    top_competitors = metrics.get("top_competitors", [])

    lead_buyer = top_buyers[0]["name"] if top_buyers else "Davlat banklari va OTMlar"
    lead_comp = top_competitors[0]["name"] if top_competitors else "Mavjud yetkazib beruvchilar"

    summary = (
        f"O'zbekiston davlat xaridlari bo'yicha tahlil qilingan {metrics['total_procedures']} "
        f"ta lotdan {metrics['it_procedures']} tasi IT toifasiga mansub bo'lib, umumiy hajmi "
        f"{it_vol_billions:,.1f} mlrd so'mni tashkil etadi. Eng yuqori byudjetga ega "
        f"buyurtmachilar: {lead_buyer} va yirik davlat tashkilotlari. "
        f"Bozorda {metrics['hot_renewals']} ta 'HOT' litsenziya yangilanish imkoniyati mavjud "
        f"bo'lib, bu Softy LLC uchun to'g'ridan-to'g'ri daromad oqimini yaratadi."
    )

    competitor_counter = (
        f"Asosiy yirik shartnomalarni egallagan kompaniyalar ({lead_comp}) "
        f"tenderlarda o'rtacha 10-15% ustama bilan ishlamoqda, biroq xizmat ko'rsatish davrida "
        f"mijozlar bilan proaktiv muloqot va qayta litsenziyalash muddatlarini kuzatib bormaydi. "
        f"Softy LLC uchun g'alaba kaliti — litsenziya tugashidan 45-60 kun oldin buyurtmachining "
        f"mas'ul IT xodimiga distribyutor narxidagi tayyor TOR va taklif bilan chiqishdir."
    )

    pricing_policy = (
        "1. >500 mln so'mlik yirik lotlar: 3.5% - 5.0% maxsus Project Price.\n"
        "2. 100 - 500 mln so'mlik o'rta lotlar: 5.0% - 7.5% moslashuvchan narx.\n"
        "3. <100 mln so'mlik e-shop xaridlari: bepul 1 yillik SLA va o'rnatish servisi."
    )

    renewal_plan = (
        f"Tizimda aniqlangan {metrics['total_renewals']} ta shartnomalar bo'yicha Renewal Radar "
        f"taqvimi shakllantirildi. Eng yuqori ballga ega 20 ta shartnoma mijozlariga Telegram bot "
        f"va CRM orqali shaxsiylashtirilgan takliflar yuboriladi."
    )

    milestones = [
        "1-qadam: HOT (score >= 80) bo'lgan top mijozlarning IT rahbarlari bilan aloqa o'rnatish.",
        "2-qadam: Yirik buyurtmachilar xarid rejalariga Softy mahsulotlarini kiritish.",
        f"3-qadam: {lead_comp} yutgan lotlar bo'yicha mijozlarga muqobil taklif berish.",
        "4-qadam: Haftalik yangi tenderlarni Telegram bot orqali nazorat qilib, taklif kiritish.",
    ]

    return {
        "engine": "SOFTY Strategic Business Advisor (Uzbekistan B2B Engine)",
        "executive_summary": summary,
        "target_segments": [
            "Davlat va tijorat banklari (Axborot xavfsizligi va Microsoft litsenziyalari)",
            "Vazirlik va davlat qo'mitalari (Infratuzilma, tarmoq va server dasturlari)",
            "Yirik oliy ta'lim muassasalari (Talabalar va o'qituvchilar uchun dasturiy ta'minot)",
            "Tibbiyot va hududiy boshqarmalar (Standart ofis va antivirus paketlari)",
        ],
        "competitor_counter_strategy": competitor_counter,
        "pricing_and_discount_policy": pricing_policy,
        "renewal_attack_plan": renewal_plan,
        "actionable_milestones": milestones,
    }


def format_macro_strategy(strategy: dict[str, Any]) -> str:
    """Format macro strategy into an executive report for display or Telegram."""
    metrics = strategy.get("metrics", {})
    it_vol = metrics.get("it_volume_uzs", 0)
    it_pct = metrics.get("it_share_pct", 0)
    it_cnt = metrics.get("it_procedures", 0)
    tot_ren = metrics.get("total_renewals", 0)
    hot_ren = metrics.get("hot_renewals", 0)

    lines = [
        "🎯 *SOFTY BIZNES STRATEGIYASI VA BOZOR TAHLILI*",
        f"⚙️ Tahlil mexanizmi: {strategy.get('engine', 'Expert AI')}",
        "",
        "📊 *Bozor hajmi va statistika:*",
        f"• Tahlil qilingan lotlar: *{metrics.get('total_procedures', 0):,} ta*",
        f"• IT xaridlari: *{it_cnt:,} ta* ({it_pct}%)",
        f"• IT bozor qiymati: *{it_vol:,.0f} UZS*",
        f"• Yangilanish imkoniyatlari: *{tot_ren} ta* (HOT: *{hot_ren} ta*)",
        "",
        "📌 *Rahbariyat uchun xulosa:*",
        strategy.get("executive_summary", ""),
        "",
        "🏢 *Maqsadli mijozlar segmentlari:*",
    ]
    for seg in strategy.get("target_segments", []):
        lines.append(f"  ✓ {seg}")

    lines.extend([
        "",
        "⚔️ *Raqobatchilarga qarshi taktika:*",
        strategy.get("competitor_counter_strategy", ""),
        "",
        "💰 *Tavsiya etiladigan narx va chegirma siyosati:*",
        strategy.get("pricing_and_discount_policy", ""),
        "",
        "🚀 *Savdo bo'limi uchun harakatlar rejasi:*",
    ])
    for ms in strategy.get("actionable_milestones", []):
        lines.append(f"  {ms}")

    return "\n".join(lines)


def format_lot_recommendation(rec: dict[str, Any]) -> str:
    """Format single lot AI recommendation into a clean report."""
    proc = rec.get("procedure", {})
    cust = proc.get("customer", {})
    curr = proc.get("currency", "UZS")
    sugg_p = rec.get("suggested_price", 0)
    lead_d = rec.get("optimal_contact_days_before", 30)

    lines = [
        f"💡 *AI BIZNES TAVSIYASI: LOT #{proc.get('source_id')}*",
        f"🏷 {proc.get('title')}",
        f"🏢 Buyurtmachi: *{cust.get('name', 'Noma\'lum')}*",
        f"💵 Summa: *{proc.get('amount', 0):,.0f} {curr}*",
        f"⚙️ Maslahatchi: {rec.get('engine', 'AI')}",
        "",
        "🔍 *Tahlil:*",
        rec.get("analysis", ""),
        "",
        "⚔️ *Raqobatchi zaifligi:*",
        rec.get("competitor_weakness", ""),
        "",
        "🎯 *Tavsiya etiladigan strategiya:*",
        rec.get("recommended_strategy", ""),
        f"• Tavsiya etiladigan chegirma: *{rec.get('suggested_discount_percent', 0)}%*",
        f"• Tavsiya etiladigan narx: *{sugg_p:,.0f} {curr}*",
        f"• Optimal bog'lanish vaqti: *{lead_d} kun oldin*",
        "",
        "📋 *Harakatlar rejasi:*",
    ]
    for step in rec.get("action_plan", []):
        lines.append(f"  {step}")

    pitch = rec.get("commercial_pitch")
    if pitch:
        lines.extend([
            "",
            "✉️ *Tayyor tijoriy taklif matni:*",
            pitch,
        ])

    return "\n".join(lines)

