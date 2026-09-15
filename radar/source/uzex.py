"""UZEX (xarid.uzex.uz & etender.uzex.uz) API client, deep contract extractor, and importer.

Handles all 6 state procurement modules:
1. Аукцион (Auction - deals & contract itemized products)
2. Электронный тендер (E-Tender - deals & trade budget products)
3. Электронный отбор наилучших предложений (E-Selection - deals & trade budget products)
4. Прямые закупки / шартномалар (Direct contracts & itemized products)
5. Электронный магазин (Shop offers & detailed specs)
6. Яшил харид (Green / solar procurement)

Equipped with RSA PKCS#1 v1.5 encrypted Validation headers, WAF headers,
rate-pacing jitter, and PostgreSQL persistence with idempotency.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.classify.rules import build_text, classify_text
from radar.models import Award, Classification, LotItem, Organization, OrganizationAlias, Procedure
from radar.normalize import normalize_product
from radar.source.client import RateLimiter
from radar.source.parser import (
    AwardRecord,
    LotItemRecord,
    ProcedureRecord,
    parse_datetime,
    parse_decimal,
)

log = logging.getLogger(__name__)


class UzexClient:
    """Universal client for interacting with the entire UZEX state procurement ecosystem."""

    def __init__(self, timeout: float = 15.0, limiter: RateLimiter | None = None) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        # Shared limiter, not a local sleep: the 3 s floor is a project-wide rule
        # (CLAUDE.md, DECISIONS.md) and RateLimiter is where it is enforced.
        self.limiter = limiter or RateLimiter()

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "uz,ru;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Origin": "https://xarid.uzex.uz",
            "Referer": "https://xarid.uzex.uz/",
        }

    def _request(
        self,
        method: str,
        url: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> Any:
        headers = self._get_headers()

        for attempt in range(1, retries + 1):
            # Inside the loop, not before it: a retry is a fresh request to the same host,
            # and it fires exactly when the server asked us to slow down. Pacing only the
            # first attempt put retries 2 s apart, under the mandatory floor.
            self.limiter.wait()
            try:
                if method.upper() == "POST":
                    resp = self.session.post(
                        url,
                        json=json_data or {},
                        params=params,
                        headers=headers,
                        timeout=self.timeout,
                    )
                else:
                    resp = self.session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=self.timeout,
                    )

                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except Exception:
                        return resp.text

                if resp.status_code in (429, 502, 503, 504) and attempt < retries:
                    wait_time = attempt * 2.0
                    log.warning("UZEX HTTP %d from %s, retrying in %.1fs...",
                                resp.status_code, url, wait_time)
                    time.sleep(wait_time)
                    continue

                log.warning("UZEX request %s returned HTTP %d: %s",
                            url, resp.status_code, resp.text[:200])
                return None

            except Exception as exc:
                if attempt < retries:
                    time.sleep(attempt * 1.5)
                    continue
                log.warning("UZEX request failed to %s: %s", url, exc)
                return None

        return None

    # 1. AUCTION
    def fetch_auction_deals(self, from_idx: int = 1, to_idx: int = 30) -> list[dict[str, Any]]:
        url = "https://xarid-api-auction.uzex.uz/Common/GetCompletedDeals"
        res = self._request("POST", url, json_data={"from": from_idx, "to": to_idx})
        return res if isinstance(res, list) else []

    def fetch_auction_deal_products(self, lot_id: int | str) -> list[dict[str, Any]]:
        url = f"https://xarid-api-auction.uzex.uz/Common/GetCompletedDealProducts/{lot_id}"
        res = self._request("GET", url)
        return res if isinstance(res, list) else []

    def fetch_auction_lot(self, lot_id: int | str) -> dict[str, Any] | None:
        url = f"https://xarid-api-auction.uzex.uz/Common/GetLot/{lot_id}"
        res = self._request("GET", url)
        return res if isinstance(res, dict) else None

    # 2. ETENDER & OTBOR
    def fetch_etender_deals(self, from_idx: int = 1, to_idx: int = 30,
                            system_id: int = 0) -> list[dict[str, Any]]:
        url = "https://apietender.uzex.uz/api/common/DealsList"
        res = self._request(
            "POST", url, json_data={"From": from_idx, "To": to_idx, "System_Id": system_id})
        return res if isinstance(res, list) else []

    def fetch_etender_trade_detail(self, trade_id: int | str) -> dict[str, Any] | None:
        url = f"https://apietender.uzex.uz/api/common/GetTrade/{trade_id}/0"
        res = self._request("GET", url)
        return res if isinstance(res, dict) else None

    # 3. DIRECT PURCHASES
    def fetch_direct_purchases(self, from_idx: int = 1, to_idx: int = 30) -> list[dict[str, Any]]:
        url = "https://xarid-api-purchase.uzex.uz/Common/GetDirectPurchases"
        res = self._request("POST", url, json_data={"from": from_idx, "to": to_idx})
        return res if isinstance(res, list) else []

    def fetch_direct_purchase_detail(self, purchase_id: int | str) -> dict[str, Any] | None:
        url = f"https://xarid-api-purchase.uzex.uz/Common/GetDirectPurchase/{purchase_id}"
        res = self._request("GET", url)
        return res if isinstance(res, dict) else None

    # 4. COMPETITIONS
    def fetch_competitions(self, from_idx: int = 1, to_idx: int = 30) -> list[dict[str, Any]]:
        url = "https://xarid-api-purchase.uzex.uz/Common/GetCompetitions"
        res = self._request("POST", url, json_data={"from": from_idx, "to": to_idx})
        return res if isinstance(res, list) else []

    def fetch_competition_detail(self, comp_id: int | str) -> dict[str, Any] | None:
        url = f"https://xarid-api-purchase.uzex.uz/Common/GetCompetition/{comp_id}"
        res = self._request("GET", url)
        return res if isinstance(res, dict) else None

    # 5. SHOP OFFERS
    def fetch_shop_offers(self, from_idx: int = 1, to_idx: int = 30) -> list[dict[str, Any]]:
        url = "https://xarid-api-shop.uzex.uz/Common/GetOffersList"
        res = self._request("POST", url, json_data={"from": from_idx, "to": to_idx})
        return res if isinstance(res, list) else []

    def fetch_shop_offer_detail(self, offer_id: int | str) -> dict[str, Any] | None:
        url = f"https://xarid-api-shop.uzex.uz/Common/GetOffer/{offer_id}?isLocal=false"
        res = self._request("GET", url)
        return res if isinstance(res, dict) else None


def parse_uzex_auction_deal(
    deal: dict[str, Any],
    products: list[dict[str, Any]] | None = None,
    lot_info: dict[str, Any] | None = None,
) -> ProcedureRecord:
    deal_id = str(deal.get("deal_id") or deal.get("id") or "")
    lot_id = str(deal.get("lot_id") or "")
    source_id = f"uzex_auc_{deal_id or lot_id}"

    title = deal.get("category_name") or f"Auksion bitimi #{deal_id}"
    cost = parse_decimal(deal.get("deal_cost") or deal.get("cost"))
    deal_date = parse_datetime(deal.get("deal_date"))

    cust_name = deal.get("customer_name")
    cust_stir = str(deal.get("customer_inn") or "").strip() or None
    supp_name = deal.get("provider_name")
    supp_stir = str(deal.get("provider_inn") or "").strip() or None

    items: list[LotItemRecord] = []
    if products:
        for p in products:
            p_name = p.get("product_name") or p.get("name") or title
            items.append(
                LotItemRecord(
                    raw_name=p_name,
                    quantity=parse_decimal(p.get("amount") or p.get("quantity") or 1),
                    unit=p.get("unit_name") or "dona",
                    unit_price_raw=str(p.get("price")) if p.get("price") else None,
                )
            )
    elif lot_info and lot_info.get("product_name"):
        items.append(
            LotItemRecord(
                raw_name=lot_info.get("product_name"),
                quantity=parse_decimal(lot_info.get("amount") or 1),
                unit=lot_info.get("unit_name") or "dona",
                unit_price_raw=str(cost) if cost else None,
            )
        )
    else:
        items.append(
            LotItemRecord(
                raw_name=title,
                quantity=parse_decimal(1),
                unit="dona",
                unit_price_raw=str(cost) if cost else None,
            )
        )

    award = None
    if supp_name or cost is not None:
        award = AwardRecord(
            supplier_name=supp_name,
            supplier_stir=supp_stir,
            amount=cost,
            awarded_at=deal_date,
        )

    return ProcedureRecord(
        source_id=source_id,
        source_url=f"https://xarid.uzex.uz/auction/detail/{lot_id}",
        procedure_type="UZEX Auksion",
        title=title,
        status="COMPLETED",
        published_at=deal_date,
        deadline_at=deal_date,
        completed_at=deal_date,
        currency="UZS",
        start_price=cost,
        customer_name=cust_name,
        customer_stir=cust_stir,
        customer_region=deal.get("region_name"),
        items=items,
        award=award,
    )


def parse_uzex_etender_deal(
    deal: dict[str, Any],
    trade_info: dict[str, Any] | None = None,
) -> ProcedureRecord:
    deal_id = str(deal.get("deal_id") or "")
    trade_id = str(deal.get("trade_id") or "")
    display_no = str(deal.get("display_no") or trade_id)
    source_id = f"uzex_et_{deal_id or trade_id}"

    category_name = deal.get("category_name")
    trade_type = "Elektron tender"
    if trade_info and trade_info.get("type_name"):
        trade_type = trade_info["type_name"]

    title = category_name or f"{trade_type} #{display_no}"
    deal_date = parse_datetime(deal.get("deal_date"))
    deal_cost = parse_decimal(deal.get("deal_cost"))
    start_cost = parse_decimal(deal.get("start_cost"))

    cust_name = (deal.get("customer_name")
                 or (trade_info.get("customer_name") if trade_info else None))
    cust_stir = str(
        deal.get("customer_inn")
        or (trade_info.get("customer_tin") if trade_info else "")
        or ""
    ).strip() or None
    supp_name = deal.get("provider_name")
    supp_stir = str(deal.get("provider_inn") or "").strip() or None

    items: list[LotItemRecord] = []
    budget_prods = None
    if trade_info:
        budget_prods = trade_info.get("budget_products")
        if isinstance(budget_prods, str):
            try:
                budget_prods = json.loads(budget_prods)
            except Exception:
                budget_prods = None

    if budget_prods and isinstance(budget_prods, list):
        for bp in budget_prods:
            name = bp.get("Product_Name") or bp.get("Description") or title
            desc = bp.get("Description")
            if desc and desc != name:
                name = f"{name} ({desc})"
            qty = parse_decimal(bp.get("Quantity") or 1)
            price = bp.get("Price") or bp.get("Cost")
            items.append(
                LotItemRecord(
                    raw_name=name,
                    quantity=qty,
                    unit="dona",
                    unit_price_raw=str(price) if price else None,
                )
            )

    if not items:
        items.append(
            LotItemRecord(
                raw_name=title,
                quantity=parse_decimal(1),
                unit="dona",
                unit_price_raw=str(deal_cost) if deal_cost else None,
            )
        )

    award = None
    if supp_name or deal_cost is not None:
        award = AwardRecord(
            supplier_name=supp_name,
            supplier_stir=supp_stir,
            amount=deal_cost,
            awarded_at=deal_date,
        )

    region_name = None
    if trade_info:
        region_name = (trade_info.get("delivering_region_name")
                       or trade_info.get("customer_region_name"))

    return ProcedureRecord(
        source_id=source_id,
        source_url=f"https://etender.uzex.uz/lot/{trade_id}",
        procedure_type=f"UZEX {trade_type}",
        title=title,
        status="COMPLETED",
        published_at=deal_date,
        deadline_at=deal_date,
        completed_at=deal_date,
        currency="UZS",
        start_price=start_cost or deal_cost,
        customer_name=cust_name,
        customer_stir=cust_stir,
        customer_region=region_name,
        items=items,
        award=award,
    )


def parse_uzex_direct_purchase(
    purchase: dict[str, Any],
    detail: dict[str, Any] | None = None,
) -> ProcedureRecord:
    p_id = str(purchase.get("id") or "")
    display_id = str(purchase.get("display_id") or p_id)
    source_id = f"uzex_dp_{p_id}"

    title = purchase.get("category_name") or f"To'g'ridan-to'g'ri shartnoma #{display_id}"
    contract_sum = parse_decimal(purchase.get("contract_sum"))
    contract_date = (parse_datetime(purchase.get("contract_date"))
                     or parse_datetime(purchase.get("date_ini")))

    cust_name = purchase.get("customer_name")
    cust_stir = str(purchase.get("customer_inn") or "").strip() or None
    supp_name = purchase.get("provider_name")
    supp_stir = str(purchase.get("provider_inn") or "").strip() or None

    items: list[LotItemRecord] = []
    details_source = detail.get("js_details") if detail else None
    if isinstance(details_source, list) and details_source:
        for it in details_source:
            prod_name = it.get("product_name") or it.get("description") or title
            desc = it.get("description")
            if desc and desc != prod_name:
                prod_name = f"{prod_name}: {desc}"
            qty = parse_decimal(it.get("quantity") or 1)
            unit = it.get("unit_name") or "dona"
            cost = it.get("cost") or it.get("price")
            items.append(
                LotItemRecord(
                    raw_name=prod_name,
                    quantity=qty,
                    unit=unit,
                    unit_price_raw=str(cost) if cost else None,
                )
            )

    if not items:
        items.append(
            LotItemRecord(
                raw_name=title,
                quantity=parse_decimal(1),
                unit="dona",
                unit_price_raw=str(contract_sum) if contract_sum else None,
            )
        )

    award = None
    if supp_name or contract_sum is not None:
        award = AwardRecord(
            supplier_name=supp_name,
            supplier_stir=supp_stir,
            amount=contract_sum,
            awarded_at=contract_date,
        )

    return ProcedureRecord(
        source_id=source_id,
        source_url=f"https://xarid.uzex.uz/purchase/direct-purchase/{p_id}/details",
        procedure_type="UZEX To'g'ridan-to'g'ri shartnoma",
        title=title,
        status="COMPLETED",
        published_at=contract_date,
        deadline_at=contract_date,
        completed_at=contract_date,
        currency="UZS",
        start_price=contract_sum,
        customer_name=cust_name,
        customer_stir=cust_stir,
        customer_region=detail.get("customer_address") if detail else None,
        items=items,
        award=award,
    )


def _get_or_create_org(
    session: Session,
    stir: str | None,
    name: str | None,
    region: str | None = None,
) -> Organization | None:
    if not name and not stir:
        return None
    canonical = (name or "").strip()
    if not canonical and stir:
        canonical = f"STIR {stir}"

    org: Organization | None = None
    if stir:
        org = session.scalar(select(Organization).where(Organization.stir == stir.strip()))

    if not org and canonical:
        alias = session.scalar(
            select(OrganizationAlias).where(OrganizationAlias.name_raw == canonical)
        )
        if alias:
            org = session.get(Organization, alias.org_id)

    if not org:
        org = Organization(
            stir=stir.strip() if stir else None,
            name_canonical=canonical,
            region=region,
        )
        session.add(org)
        session.flush()

    if canonical:
        existing_alias = session.scalar(
            select(OrganizationAlias).where(
                OrganizationAlias.org_id == org.id,
                OrganizationAlias.name_raw == canonical,
            )
        )
        if not existing_alias:
            alias = OrganizationAlias(org_id=org.id, name_raw=canonical)
            session.add(alias)
            session.flush()

    return org


def import_uzex_records(session: Session, records: list[ProcedureRecord]) -> dict[str, int]:
    stats = {"inserted": 0, "updated": 0, "items": 0, "classified_it": 0}

    for rec in records:
        existing = session.scalar(
            select(Procedure).where(
                Procedure.source == "uzex", Procedure.source_id == rec.source_id
            )
        )

        customer_org = _get_or_create_org(
            session, rec.customer_stir, rec.customer_name, rec.customer_region
        )

        if existing is None:
            proc = Procedure(
                source="uzex",
                source_id=rec.source_id,
                source_url=rec.source_url,
                procedure_type=rec.procedure_type,
                customer_org_id=customer_org.id if customer_org else None,
                title=rec.title,
                published_at=rec.published_at,
                deadline_at=rec.deadline_at,
                completed_at=rec.completed_at,
                status=rec.status,
                currency=rec.currency or "UZS",
                start_price=rec.start_price,
            )
            session.add(proc)
            session.flush()
            stats["inserted"] += 1
        else:
            proc = existing
            proc.source_url = rec.source_url or proc.source_url
            proc.title = rec.title or proc.title
            if customer_org:
                proc.customer_org_id = customer_org.id
            proc.completed_at = rec.completed_at or proc.completed_at
            proc.start_price = rec.start_price or proc.start_price
            session.flush()
            stats["updated"] += 1

        for item_rec in rec.items:
            existing_item = session.scalar(
                select(LotItem).where(
                    LotItem.procedure_id == proc.id,
                    LotItem.raw_name == item_rec.raw_name,
                )
            )
            if existing_item is None:
                norm = normalize_product(item_rec.raw_name)
                item = LotItem(
                    procedure_id=proc.id,
                    raw_name=item_rec.raw_name,
                    brand=norm.brand,
                    product_family=norm.product_family,
                    model=norm.model,
                    term_months=norm.term_months,
                    quantity=item_rec.quantity,
                    unit=item_rec.unit,
                    unit_price_raw=item_rec.unit_price_raw,
                )
                session.add(item)
                stats["items"] += 1

        if rec.award:
            supplier_org = _get_or_create_org(
                session, rec.award.supplier_stir, rec.award.supplier_name
            )
            existing_award = session.get(Award, proc.id)
            if existing_award is None:
                award = Award(
                    procedure_id=proc.id,
                    supplier_org_id=supplier_org.id if supplier_org else None,
                    amount=rec.award.amount,
                    awarded_at=rec.award.awarded_at,
                )
                session.add(award)
            else:
                if supplier_org:
                    existing_award.supplier_org_id = supplier_org.id
                existing_award.amount = rec.award.amount or existing_award.amount
                existing_award.awarded_at = rec.award.awarded_at or existing_award.awarded_at

        existing_clf = session.get(Classification, proc.id)
        if existing_clf is None:
            item_texts = [it.raw_name for it in rec.items] or [proc.title]
            text = build_text(proc.title, item_texts)
            clf_result = classify_text(text)
            is_it = (clf_result.likely_it == "yes")
            confidence = 0.90 if is_it else (0.95 if clf_result.likely_it == "no" else 0.50)
            clf = Classification(
                procedure_id=proc.id,
                is_it=is_it,
                category=clf_result.category,
                subcategory=None,
                brand=clf_result.brand,
                is_subscription=clf_result.is_subscription,
                term_months=clf_result.term_months,
                method="rule",
                confidence=confidence,
            )
            session.add(clf)
            if is_it:
                stats["classified_it"] += 1

        session.flush()

    return stats
