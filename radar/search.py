"""Tender Radar — Advanced Search & Intelligence Engine.

Provides 3 core intelligence dimensions:
1. Keyword Search (Lot title, items, brand, category across all platforms).
2. Customer Intelligence (Purchasing history, total spend, suppliers, timeline).
3. Competitor Intelligence (Winning history, revenues, customers sold to, market share).
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from radar.models import Award, Classification, LotItem, Organization, OrganizationAlias, Procedure


def search_keywords(
    session: Session,
    query: str,
    limit: int = 50,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Search procedures and contract items by keyword across titles, items, and brands."""
    q_str = query.strip()
    if not q_str:
        return []

    pattern = f"%{q_str}%"

    # Base query joining procedure, customer, award, items, and classification
    stmt = (
        select(Procedure)
        .options(
            joinedload(Procedure.customer),
            joinedload(Procedure.award).joinedload(Award.supplier),
            joinedload(Procedure.items),
            joinedload(Procedure.classification),
        )
        .outerjoin(Procedure.items)
        .outerjoin(Procedure.classification)
        .where(
            or_(
                Procedure.title.ilike(pattern),
                Procedure.source_id.ilike(pattern),
                LotItem.raw_name.ilike(pattern),
                LotItem.brand.ilike(pattern),
                LotItem.product_family.ilike(pattern),
                Classification.category.ilike(pattern),
            )
        )
        .distinct()
        .order_by(Procedure.completed_at.desc().nullslast(), Procedure.id.desc())
        .limit(limit)
    )

    if source:
        stmt = stmt.where(Procedure.source == source)

    procs = list(session.scalars(stmt).unique())
    results = []

    for p in procs:
        cust = p.customer
        aw = p.award
        supp = aw.supplier if aw else None
        clf = p.classification

        dt = (
            p.completed_at.strftime("%Y-%m-%d")
            if p.completed_at
            else (p.published_at.strftime("%Y-%m-%d") if p.published_at else None)
        )
        amt = float(aw.amount if (aw and aw.amount is not None) else (p.start_price or 0))
        supp_name = supp.name_canonical if supp else None

        results.append({
            "id": p.id,
            "source": p.source,
            "source_id": p.source_id,
            "source_url": p.source_url,
            "title": p.title,
            "procedure_type": p.procedure_type,
            "status": p.status,
            "date": dt,
            "amount": amt,
            "currency": p.currency or "UZS",
            "customer": {
                "name": cust.name_canonical if cust else "Noma'lum",
                "stir": cust.stir if cust else None,
                "region": cust.region if cust else None,
            },
            "supplier": {
                "name": supp_name,
                "stir": supp.stir if supp else None,
            } if aw else None,
            "items": [
                {
                    "raw_name": itm.raw_name,
                    "brand": itm.brand,
                    "product_family": itm.product_family,
                    "quantity": float(itm.quantity) if itm.quantity is not None else None,
                    "unit": itm.unit,
                }
                for itm in p.items
            ],
            "classification": {
                "is_it": clf.is_it if clf else False,
                "category": clf.category if clf else None,
                "brand": clf.brand if clf else None,
            } if clf else None,
        })

    return results


def search_customer_intelligence(
    session: Session,
    query: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Retrieve full procurement history, suppliers, and metrics for a buyer/customer."""
    q_str = query.strip()
    if not q_str:
        return {"found": False, "organizations": []}

    pattern = f"%{q_str}%"

    # Find matching organizations
    orgs = list(
        session.scalars(
            select(Organization)
            .outerjoin(Organization.aliases)
            .where(
                or_(
                    Organization.stir.ilike(pattern),
                    Organization.name_canonical.ilike(pattern),
                    OrganizationAlias.name_raw.ilike(pattern),
                )
            )
            .distinct()
            .limit(10)
        )
    )

    if not orgs:
        return {"found": False, "query": q_str, "organizations": []}

    org_results = []
    for org in orgs:
        procs = list(
            session.scalars(
                select(Procedure)
                .options(
                    joinedload(Procedure.award).joinedload(Award.supplier),
                    joinedload(Procedure.items),
                    joinedload(Procedure.classification),
                )
                .where(Procedure.customer_org_id == org.id)
                .order_by(Procedure.completed_at.desc().nullslast(), Procedure.id.desc())
                .limit(limit)
            ).unique()
        )

        total_spent = Decimal(0)
        category_counts: Counter[str] = Counter()
        supplier_counts: Counter[str] = Counter()
        purchases = []

        for p in procs:
            aw = p.award
            supp = aw.supplier if aw else None
            amount = aw.amount if (aw and aw.amount is not None) else (p.start_price or Decimal(0))
            total_spent += amount

            supp_name = supp.name_canonical if supp else "Noma'lum yetkazib beruvchi"
            supplier_counts[supp_name] += 1

            cat = p.classification.category if (p.classification and p.classification.category) \
                else "Boshqa"
            category_counts[cat] += 1

            p_date = (
                p.completed_at.strftime("%Y-%m-%d")
                if p.completed_at
                else (p.published_at.strftime("%Y-%m-%d") if p.published_at else None)
            )
            purchases.append({
                "procedure_id": p.id,
                "source": p.source,
                "source_id": p.source_id,
                "source_url": p.source_url,
                "title": p.title,
                "date": p_date,
                "amount": float(amount),
                "currency": p.currency or "UZS",
                "supplier": {
                    "name": supp_name,
                    "stir": supp.stir if supp else None,
                },
                "category": cat,
                "items": [
                    {
                        "name": it.raw_name,
                        "brand": it.brand,
                        "family": it.product_family,
                        "quantity": float(it.quantity) if it.quantity is not None else None,
                    }
                    for it in p.items
                ],
            })

        avg_contract = float(total_spent / len(procs)) if procs else 0.0

        org_results.append({
            "org_id": org.id,
            "name": org.name_canonical,
            "stir": org.stir,
            "region": org.region,
            "total_purchases_count": len(procs),
            "total_spent": float(total_spent),
            "avg_contract_size": avg_contract,
            "top_categories": [
                {"category": k, "count": v} for k, v in category_counts.most_common(5)
            ],
            "top_suppliers": [
                {"supplier": k, "count": v} for k, v in supplier_counts.most_common(5)
            ],
            "purchases": purchases,
        })

    return {
        "found": True,
        "query": q_str,
        "count": len(org_results),
        "organizations": org_results,
    }


def search_competitor_intelligence(
    session: Session,
    query: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Retrieve all sales, tenders won, buyers, and revenue for a competitor/supplier."""
    q_str = query.strip()
    if not q_str:
        return {"found": False, "competitors": []}

    pattern = f"%{q_str}%"

    # Find matching organizations who are recorded as suppliers in Award
    orgs = list(
        session.scalars(
            select(Organization)
            .join(Award, Award.supplier_org_id == Organization.id)
            .outerjoin(Organization.aliases)
            .where(
                or_(
                    Organization.stir.ilike(pattern),
                    Organization.name_canonical.ilike(pattern),
                    OrganizationAlias.name_raw.ilike(pattern),
                )
            )
            .distinct()
            .limit(10)
        )
    )

    if not orgs:
        return {"found": False, "query": q_str, "competitors": []}

    competitors = []
    for org in orgs:
        # Find all awards won by this supplier
        awards = list(
            session.scalars(
                select(Award)
                .options(
                    joinedload(Award.procedure).joinedload(Procedure.customer),
                    joinedload(Award.procedure).joinedload(Procedure.items),
                    joinedload(Award.procedure).joinedload(Procedure.classification),
                )
                .where(Award.supplier_org_id == org.id)
                .order_by(Award.awarded_at.desc().nullslast())
                .limit(limit)
            ).unique()
        )

        total_won = Decimal(0)
        buyer_counts: Counter[str] = Counter()
        category_counts: Counter[str] = Counter()
        deals = []

        for aw in awards:
            proc = aw.procedure
            if not proc:
                continue
            amt = aw.amount or proc.start_price or Decimal(0)
            total_won += amt

            cust = proc.customer
            cust_name = cust.name_canonical if cust else "Noma'lum buyurtmachi"
            buyer_counts[cust_name] += 1

            cat = proc.classification.category if (
                proc.classification and proc.classification.category
            ) else "Boshqa"
            category_counts[cat] += 1

            deal_date = (
                aw.awarded_at.strftime("%Y-%m-%d")
                if aw.awarded_at
                else (proc.completed_at.strftime("%Y-%m-%d") if proc.completed_at else None)
            )
            deals.append({
                "procedure_id": proc.id,
                "source": proc.source,
                "source_id": proc.source_id,
                "source_url": proc.source_url,
                "title": proc.title,
                "date": deal_date,
                "amount": float(amt),
                "currency": proc.currency or "UZS",
                "customer": {
                    "name": cust_name,
                    "stir": cust.stir if cust else None,
                    "region": cust.region if cust else None,
                },
                "category": cat,
                "products": [
                    {
                        "name": it.raw_name,
                        "brand": it.brand,
                        "family": it.product_family,
                        "quantity": float(it.quantity) if it.quantity is not None else None,
                    }
                    for it in proc.items
                ],
            })

        avg_deal = float(total_won / len(awards)) if awards else 0.0

        competitors.append({
            "org_id": org.id,
            "name": org.name_canonical,
            "stir": org.stir,
            "region": org.region,
            "total_wins_count": len(awards),
            "total_won_amount": float(total_won),
            "avg_deal_size": avg_deal,
            "top_customers": [
                {"customer": k, "count": v} for k, v in buyer_counts.most_common(5)
            ],
            "top_categories": [
                {"category": k, "count": v} for k, v in category_counts.most_common(5)
            ],
            "deals": deals,
        })

    return {
        "found": True,
        "query": q_str,
        "count": len(competitors),
        "competitors": competitors,
    }
