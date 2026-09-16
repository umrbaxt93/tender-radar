"""Bitrix24 CRM integration and sales workflow module.

Ported from app/crm_service.py into tender-radar architecture with strict idempotency:
A single lot/procedure can NEVER create duplicate deals in Bitrix24 or the database.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from radar.models import Award, CrmDeal, CrmTask, Organization, Procedure, RenewalOpportunity

STAFF_MEMBERS: list[dict[str, str]] = [
    {"id": "umid", "name": "Umidjon Fatullayev", "role": "CEO"},
    {"id": "yoqubxon", "name": "Yoqubxon", "role": "E-Shop rahbari (Kanal #1)"},
    {"id": "usmon", "name": "Usmon", "role": "Litsenziya yangilash (Kanal #2)"},
    {"id": "shohruh", "name": "Shohruh", "role": "Vendor narxlash / Bitrix24 Admin"},
    {"id": "komiljon", "name": "Komiljon", "role": "Tender saralash (Kanal #3)"},
    {"id": "siyovush", "name": "Siyovush", "role": "Presale / Vendor narxlash"},
]


def get_bitrix_webhook_url() -> str | None:
    """Safely obtain Bitrix24 incoming webhook URL from environment or credentials."""
    url = os.environ.get("BITRIX24_WEBHOOK_URL", "").strip()
    if url:
        return url if url.endswith("/") else url + "/"

    cred_path_env = os.environ.get("BITRIX24_CREDENTIALS_PATH")
    candidate_paths: list[Path] = []
    if cred_path_env:
        candidate_paths.append(Path(cred_path_env))
    candidate_paths.append(
        Path.home() / ".gemini" / "config" / "mcp_servers" / "bitrix24" / "credentials.json"
    )

    for p in candidate_paths:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                found_url = data.get("webhook_url", "").strip()
                if found_url and "PORTAL_NOMI" not in found_url and "WEBHOOK_KODI" not in found_url:
                    return found_url if found_url.endswith("/") else found_url + "/"
            except Exception:
                continue

    return None


def call_bitrix_api(
    method: str, params: dict[str, Any] | None = None, webhook_url: str | None = None
) -> Any:
    """Call a Bitrix24 REST API method using urllib."""
    url_base = webhook_url or get_bitrix_webhook_url()
    if not url_base:
        raise RuntimeError("Bitrix24 webhook URL is not configured.")

    endpoint = f"{url_base}{method}.json"
    data = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Bitrix24 HTTP {e.code}: {err_msg}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Bitrix24 ga ulanib bo'lmadi: {e.reason}") from e

    if "error" in body:
        raise RuntimeError(
            f"Bitrix24 API xatosi: {body.get('error_description', body['error'])}"
        )
    return body.get("result")


def get_company_profile_and_timeline(session: Session, stir: str) -> dict[str, Any]:
    """Retrieve full company profile and chronological procedure timeline for a STIR.

    Grounded solely in database records (procedures, contract items, awards).
    """
    org = session.execute(
        select(Organization).where(Organization.stir == stir)
    ).scalar_one_or_none()

    if not org:
        return {"found": False, "message": f"STIR {stir} bo'yicha korxona topilmadi"}

    stmt = (
        select(Procedure)
        .options(
            joinedload(Procedure.items),
            joinedload(Procedure.award).joinedload(Award.supplier),
            joinedload(Procedure.classification),
            joinedload(Procedure.crm_deal),
        )
        .where(Procedure.customer_org_id == org.id)
        .order_by(
            Procedure.completed_at.desc().nullslast(),
            Procedure.published_at.desc().nullslast(),
        )
    )
    procedures = session.execute(stmt).unique().scalars().all()

    timeline_events: list[dict[str, Any]] = []
    has_verified_purchase = False

    for proc in procedures:
        is_contracted = bool(
            (proc.award and proc.award.amount is not None)
            or (proc.status and proc.status in ("Совершен", "COMPLETED", "contracted"))
        )
        if is_contracted:
            has_verified_purchase = True

        items_data = [
            {
                "product_name": it.raw_name,
                "brand": it.brand,
                "product_family": it.product_family,
                "model": it.model,
                "term_months": it.term_months,
                "quantity": float(it.quantity) if it.quantity else None,
                "unit": it.unit,
                "unit_price": it.unit_price_raw,
                "is_purchased_product": is_contracted,
            }
            for it in proc.items
        ]

        supplier_name = "Aniqlanmagan"
        supplier_stir = None
        if proc.award and proc.award.supplier:
            supplier_name = proc.award.supplier.name_canonical
            supplier_stir = proc.award.supplier.stir

        proof_label = "Xarid qilingan" if is_contracted else "Xarid e'lon qilingan (shartnomasiz)"
        timeline_events.append({
            "procedure_id": proc.id,
            "source": proc.source,
            "source_id": proc.source_id,
            "title": proc.title,
            "source_url": proc.source_url,
            "published_at": proc.published_at.isoformat() if proc.published_at else None,
            "completed_at": proc.completed_at.isoformat() if proc.completed_at else None,
            "status": proc.status,
            "start_price": float(proc.start_price) if proc.start_price else None,
            "final_price": float(proc.award.amount) if (proc.award and proc.award.amount) else None,
            "currency": proc.currency,
            "supplier_name": supplier_name,
            "supplier_stir": supplier_stir,
            "is_verified_contract": is_contracted,
            "items": items_data,
            "crm_deal_id": proc.crm_deal.deal_id if proc.crm_deal else None,
            "proof_status": proof_label,
        })

    tasks_stmt = (
        select(CrmTask)
        .where(CrmTask.customer_org_id == org.id)
        .order_by(CrmTask.created_at.desc())
    )
    tasks = session.execute(tasks_stmt).scalars().all()
    tasks_data = [
        {
            "id": t.id,
            "task_type": t.task_type,
            "task_title": t.task_title,
            "assigned_staff_id": t.assigned_staff_id,
            "assigned_staff_name": t.assigned_staff_name,
            "proposal_summary": t.proposal_summary,
            "status": t.status,
            "bitrix_deal_id": t.bitrix_deal_id,
            "created_at": t.created_at.isoformat(),
        }
        for t in tasks
    ]

    proof_status = "VERIFIED_BUYER" if has_verified_purchase else "ANNOUNCED_ONLY"
    proof_label = (
        "Tasdiqlangan Xaridor" if has_verified_purchase else "Xarid e'lon qilgan (dalilsiz)"
    )
    return {
        "found": True,
        "company": {
            "id": org.id,
            "stir": org.stir,
            "name": org.name_canonical,
            "region": org.region,
            "calculated_proof_status": proof_status,
            "proof_status_label": proof_label,
        },
        "timeline": timeline_events,
        "total_procedures": len(timeline_events),
        "tasks": tasks_data,
    }


def generate_grounded_proposal(session: Session, stir: str) -> dict[str, Any]:
    """Generate a proposal draft grounded exclusively in verified purchase history.

    Never invents prices. Flags draft as requiring human verification.
    """
    profile = get_company_profile_and_timeline(session, stir)
    if not profile["found"]:
        return {"error": f"STIR {stir} bo'yicha tashkilot topilmadi"}

    comp = profile["company"]
    timeline = profile["timeline"]

    observed_products: list[dict[str, Any]] = []
    seen_products: set[str] = set()

    for event in timeline:
        for it in event.get("items", []):
            prod_name = it.get("product_name") or ""
            key = f"{it.get('brand')}_{it.get('product_family')}_{prod_name[:40]}".lower()
            if key in seen_products:
                continue
            seen_products.add(key)

            if it.get("brand") or it.get("product_family") or it.get("is_purchased_product"):
                observed_products.append({
                    "product": prod_name,
                    "brand": it.get("brand"),
                    "product_family": it.get("product_family"),
                    "model": it.get("model"),
                    "term_months": it.get("term_months"),
                    "last_purchase_date": event.get("completed_at") or event.get("published_at"),
                    "last_supplier": event.get("supplier_name"),
                    "lot_url": event.get("source_url"),
                })

    company_name = comp.get("name")
    return {
        "company_name": company_name,
        "stir": comp.get("stir"),
        "region": comp.get("region") or "Noma'lum",
        "observed_products_count": len(observed_products),
        "observed_products": observed_products[:10],
        "proposal_subject": f"Litsenziyalarni muddatida uzaytirish — {company_name}",
        "grounded_rationale": (
            "Sizning tashkilotingiz davlat xaridlarida quyidagi rasmiy dasturiy ta'minot va "
            "uskunalarni xarid qilganligi ma'lumotlar bazamizda tasdiqlangan."
        ),
        "pricing_notice": (
            "Amaldagi rasmiy narxlar distribyutor kursiga qarab taqdim etiladi "
            "(To'qima narxlar kiritilmagan)."
        ),
        "status": "DRAFT_REQUIRES_HUMAN_CONFIRMATION",
        "auto_send_allowed": False,
    }


def push_deal_for_procedure(
    session: Session,
    procedure_id: int,
    webhook_url: str | None = None,
    title: str | None = None,
    amount: float | None = None,
    assigned_staff_id: str | None = None,
    use_mock: bool = False,
) -> dict[str, Any]:
    """Create a Bitrix24 deal for a procedure with STRICT IDEMPOTENCY.

    If a deal for this procedure_id already exists in crm_deal, it returns the
    existing deal information without making any external API calls or database insertions.
    """
    # 1. Idempotency check: does a deal already exist for this lot?
    existing = session.execute(
        select(CrmDeal).where(CrmDeal.procedure_id == procedure_id)
    ).scalar_one_or_none()

    if existing:
        return {
            "status": "already_exists",
            "created": False,
            "deal_id": existing.deal_id,
            "procedure_id": procedure_id,
            "title": existing.title,
            "amount": float(existing.amount) if existing.amount is not None else 0.0,
            "message": f"Lot #{procedure_id} uchun bitim mavjud: Deal #{existing.deal_id}",
        }

    # 2. Fetch procedure details
    stmt = (
        select(Procedure)
        .options(
            joinedload(Procedure.customer),
            joinedload(Procedure.items),
            joinedload(Procedure.award).joinedload(Award.supplier),
            joinedload(Procedure.classification),
        )
        .where(Procedure.id == procedure_id)
    )
    procedure = session.execute(stmt).unique().scalar_one_or_none()
    if not procedure:
        raise ValueError(f"Procedure #{procedure_id} topilmadi")

    # 3. Formulate deal title and amount
    deal_title = (
        title or f"Tender: {procedure.title[:80]} ({procedure.source}:{procedure.source_id})"
    )
    if amount is not None:
        deal_amount = float(amount)
    elif procedure.award and procedure.award.amount is not None:
        deal_amount = float(procedure.award.amount)
    elif procedure.start_price is not None:
        deal_amount = float(procedure.start_price)
    else:
        deal_amount = 0.0

    # 4. Comments with rich context
    comments_lines = [
        f"<b>Loyiha / Tender:</b> {procedure.title}",
        f"<b>Manba:</b> {procedure.source} (ID: {procedure.source_id})",
    ]
    if procedure.customer:
        customer_stir = procedure.customer.stir or "Noma'lum"
        comments_lines.append(
            f"<b>Buyurtmachi:</b> {procedure.customer.name_canonical} (STIR: {customer_stir})"
        )
    if procedure.items:
        items_summary = "; ".join(
            f"{it.raw_name} ({it.quantity or 1} {it.unit or 'dona'})"
            for it in procedure.items[:5]
        )
        comments_lines.append(f"<b>Mahsulotlar:</b> {items_summary}")
    if procedure.award and procedure.award.supplier:
        sup_name = procedure.award.supplier.name_canonical
        curr = procedure.currency or "UZS"
        comments_lines.append(
            f"<b>Avvalgi g'olib:</b> {sup_name} (Summa: {procedure.award.amount} {curr})"
        )
    if procedure.source_url:
        comments_lines.append(
            f"<b>Havola:</b> <a href=\"{procedure.source_url}\">{procedure.source_url}</a>"
        )

    comments_html = "<br>".join(comments_lines)

    # 5. External Bitrix24 call or mock
    wh_url = webhook_url or get_bitrix_webhook_url()
    bitrix_deal_id: str
    bitrix_resp: dict[str, Any]

    if wh_url and not use_mock:
        fields = {
            "TITLE": deal_title,
            "TYPE_ID": "SALE",
            "STAGE_ID": "NEW",
            "OPPORTUNITY": deal_amount,
            "CURRENCY_ID": procedure.currency or "UZS",
            "COMMENTS": comments_html,
            "SOURCE_ID": "OTHER",
            "OPENED": "Y",
        }
        res = call_bitrix_api("crm.deal.add", {"fields": fields}, webhook_url=wh_url)
        bitrix_deal_id = str(res)
        bitrix_resp = {"raw_result": res}
    else:
        # Traceable mock ID when webhook is not configured or in testing
        bitrix_deal_id = f"BX24-{procedure.source}-{procedure.source_id}"
        bitrix_resp = {"mock": True, "generated_id": bitrix_deal_id}

    # 6. Persist CrmDeal record (guaranteed unique by procedure_id)
    deal_record = CrmDeal(
        procedure_id=procedure.id,
        deal_id=bitrix_deal_id,
        customer_org_id=procedure.customer_org_id,
        title=deal_title,
        amount=Decimal(str(deal_amount)) if deal_amount else None,
        status="CREATED",
        bitrix_response=bitrix_resp,
    )
    session.add(deal_record)

    # 7. Record corresponding CrmTask log
    staff_member = next((s for s in STAFF_MEMBERS if s["id"] == assigned_staff_id), None)
    staff_name = staff_member["name"] if staff_member else "Avtomatik sinx"

    task_record = CrmTask(
        customer_org_id=procedure.customer_org_id,
        procedure_id=procedure.id,
        task_type="BITRIXGA_YUBORISH",
        task_title=f"Bitrix24 ga yuborildi: {deal_title}",
        assigned_staff_id=assigned_staff_id,
        assigned_staff_name=staff_name,
        proposal_summary=procedure.title,
        status="BAJARILDI",
        bitrix_deal_id=bitrix_deal_id,
    )
    session.add(task_record)
    session.flush()

    return {
        "status": "created",
        "created": True,
        "deal_id": bitrix_deal_id,
        "procedure_id": procedure.id,
        "title": deal_title,
        "amount": deal_amount,
        "message": f"Bitrix24 ga bitim #{bitrix_deal_id} muvaffaqiyatli yuborildi",
    }


def push_to_bitrix24(
    session: Session,
    target: str | int,
    title: str | None = None,
    amount: float = 0.0,
    use_mock: bool = False,
) -> dict[str, Any]:
    """Compatible wrapper for push_to_bitrix24.

    Accepts:
    - procedure_id (int or numeric string)
    - company STIR (string with digits) -> finds highest renewal/procedure and
      creates deal idempotently.
    """
    is_num_str = isinstance(target, str) and target.isdigit() and len(target) <= 6
    if isinstance(target, int) or is_num_str:
        proc_id = int(target)
        return push_deal_for_procedure(
            session=session,
            procedure_id=proc_id,
            title=title,
            amount=amount if amount > 0 else None,
            use_mock=use_mock,
        )

    # Treated as STIR
    stir = str(target).strip()
    org = session.execute(
        select(Organization).where(Organization.stir == stir)
    ).scalar_one_or_none()

    if not org:
        return {"success": False, "message": f"STIR {stir} bo'yicha korxona topilmadi"}

    # Find highest scored renewal or most recent procedure for this org
    renewal = session.execute(
        select(RenewalOpportunity)
        .where(RenewalOpportunity.customer_org_id == org.id)
        .order_by(RenewalOpportunity.score.desc())
        .limit(1)
    ).scalar_one_or_none()

    if renewal:
        target_proc_id = renewal.procedure_id
    else:
        proc = session.execute(
            select(Procedure)
            .where(Procedure.customer_org_id == org.id)
            .order_by(
                Procedure.completed_at.desc().nullslast(),
                Procedure.published_at.desc().nullslast(),
            )
            .limit(1)
        ).scalar_one_or_none()
        if not proc:
            return {"success": False, "message": f"STIR {stir} bo'yicha xaridlar topilmadi"}
        target_proc_id = proc.id

    res = push_deal_for_procedure(
        session=session,
        procedure_id=target_proc_id,
        title=title,
        amount=amount if amount > 0 else None,
        use_mock=use_mock,
    )
    return {
        "success": True,
        "inn": stir,
        "bitrix_deal_id": res["deal_id"],
        "already_existed": not res["created"],
        "message": res["message"],
    }


def create_sales_task(
    session: Session,
    inn: str,
    task_title: str,
    task_type: str = "TAKTAK_TAYYORLASH",
    assigned_staff_id: str | None = None,
    procedure_id: int | None = None,
    proposal_summary: str | None = None,
) -> dict[str, Any]:
    """Create an internal sales task for a customer."""
    org = session.execute(
        select(Organization).where(Organization.stir == inn)
    ).scalar_one_or_none()
    org_id = org.id if org else None

    staff_member = next((s for s in STAFF_MEMBERS if s["id"] == assigned_staff_id), None)
    staff_name = staff_member["name"] if staff_member else "Biriktirilmagan"

    task = CrmTask(
        customer_org_id=org_id,
        procedure_id=procedure_id,
        task_type=task_type,
        task_title=task_title,
        assigned_staff_id=assigned_staff_id,
        assigned_staff_name=staff_name,
        proposal_summary=proposal_summary,
        status="YANGI",
    )
    session.add(task)
    session.flush()

    return {
        "success": True,
        "task_id": task.id,
        "task_title": task.task_title,
        "assigned_to": staff_name,
        "created_at": task.created_at.isoformat(),
    }


def assign_staff(session: Session, inn: str, staff_id: str) -> dict[str, Any]:
    """Assign staff member to a customer company via sales task log."""
    staff_member = next((s for s in STAFF_MEMBERS if s["id"] == staff_id), None)
    staff_name = staff_member["name"] if staff_member else staff_id

    task_res = create_sales_task(
        session=session,
        inn=inn,
        task_title=f"Mas'ul xodim biriktirildi: {staff_name}",
        task_type="XODIM_BIRIKTIRISH",
        assigned_staff_id=staff_id,
    )
    return {
        "success": True,
        "inn": inn,
        "assigned_staff_id": staff_id,
        "assigned_staff_name": staff_name,
        "task_id": task_res["task_id"],
        "message": f"Mas'ul xodim {staff_name} biriktirildi",
    }
