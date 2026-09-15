"""E-Birja (xarid.ebirja.uz) API client, data extractor, and importer for Tender Radar.

Supports authenticated requests with E-IMZO session or public catalog queries.
Imports contracts and auctions into the radar database with idempotency.
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.classify.rules import build_text, classify_text
from radar.eimzo import EImzoManager
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

EBIRJA_BASE_URL = "https://xarid-api.ebirja.uz"


class EbirjaClient:
    """HTTP Client for interacting with E-Birja contract and auction endpoints."""

    def __init__(
        self,
        base_url: str = EBIRJA_BASE_URL,
        eimzo_mgr: EImzoManager | None = None,
        timeout: float = 12.0,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.eimzo_mgr = eimzo_mgr or EImzoManager()
        self.timeout = timeout
        self.ctx = ssl.create_default_context()
        # Shared limiter, not a local sleep: the 3 s floor is a project-wide rule
        # (CLAUDE.md, DECISIONS.md) and RateLimiter is where it is enforced.
        self.limiter = limiter or RateLimiter()

    def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        import time

        params = params or {}
        query_string = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self.base_url}{endpoint}"
        if query_string:
            url = f"{url}?{query_string}"

        headers = self.eimzo_mgr.get_auth_headers()
        headers["Origin"] = "https://ebirja.uz"
        headers["Referer"] = "https://ebirja.uz/"
        headers["Accept"] = "application/json, text/plain, */*"
        headers["Accept-Language"] = "uz,ru;q=0.9,en;q=0.8"

        self.limiter.wait()

        for attempt in range(1, retries + 1):
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, context=self.ctx, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 502, 503, 504) and attempt < retries:
                    wait_time = attempt * 2.5
                    log.warning(
                        "HTTP %d from %s, retrying in %.1fs (attempt %d/%d)",
                        exc.code,
                        url,
                        wait_time,
                        attempt,
                        retries,
                    )
                    time.sleep(wait_time)
                    continue
                log.warning("HTTP error %d from %s", exc.code, url)
                return {
                    "error": f"HTTP {exc.code}",
                    "result": {"data": [], "meta": {"totalCount": 0}},
                }
            except Exception as exc:
                if attempt < retries:
                    time.sleep(attempt * 1.5)
                    continue
                log.warning("Request failed to %s: %s", url, exc)
                return {"error": str(exc), "result": {"data": [], "meta": {"totalCount": 0}}}

        return {"error": "Max retries exceeded", "result": {"data": [], "meta": {"totalCount": 0}}}

    def fetch_contract_view(self, contract_id: int | str) -> dict[str, Any]:
        """Fetch detailed contract information using authenticated session."""
        return self._request("/common/contract/view", {"id": str(contract_id)})

    def fetch_shop_contracts(
        self,
        page: int = 0,
        per_page: int = 20,
        search: str | None = None,
        shop_type: str = "e-shop",
    ) -> dict[str, Any]:
        """Fetch electronic shop or national shop contracts."""
        params = {
            "type": shop_type,
            "currentPage": page,
            "perPage": per_page,
        }
        if search:
            params["search"] = search
        return self._request("/common/contract/shop-list", params)

    def fetch_tender_contracts(
        self,
        page: int = 0,
        per_page: int = 20,
        search: str | None = None,
        tender_type: int = 1,
    ) -> dict[str, Any]:
        """Fetch tender (type=1) or selection (type=2) contracts."""
        params = {
            "type": tender_type,
            "currentPage": page,
            "perPage": per_page,
        }
        if search:
            params["search"] = search
        return self._request("/common/contract/external-tender", params)

    def fetch_offer_requests(
        self,
        page: int = 0,
        per_page: int = 20,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Fetch offer request contracts."""
        params = {
            "currentPage": page,
            "perPage": per_page,
        }
        if search:
            params["search"] = search
        return self._request("/common/contract/external-offer-request", params)

    def fetch_active_auctions(
        self,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Fetch active/ongoing auctions."""
        params = {
            "page": page,
            "size": size,
        }
        if search:
            params["search"] = search
        return self._request("/auction/auction/active", params)


def parse_ebirja_contract(raw: dict[str, Any], contract_type: str = "Shartnoma") -> ProcedureRecord:
    """Convert raw E-Birja contract dictionary into normalized ProcedureRecord."""
    contract_id = str(raw.get("id") or "")
    contract_num = raw.get("number") or f"XD_{contract_id}"
    order = raw.get("order") or {}
    tender = raw.get("tender") or {}
    offer = raw.get("offer_request") or {}

    # Title resolution
    title = (
        order.get("title")
        or tender.get("title")
        or offer.get("title")
        or f"E-Birja shartnoma {contract_num} ({contract_type})"
    )

    created_at = parse_datetime(raw.get("created_at"))
    price = parse_decimal(raw.get("price"))
    currency = "UZS" if str(raw.get("currency")) in ("000", "UZS", "") else str(raw.get("currency"))

    # Customer & Producer
    customer = raw.get("customer") or {}
    producer = raw.get("producer") or {}

    cust_name = customer.get("title") or customer.get("name")
    cust_stir = customer.get("tin") or customer.get("inn")
    cust_region = customer.get("region") if isinstance(customer.get("region"), str) else None

    supp_name = producer.get("title") or producer.get("name")
    supp_stir = producer.get("tin") or producer.get("inn")

    award = None
    if supp_name or price is not None:
        award = AwardRecord(
            supplier_name=supp_name,
            supplier_stir=supp_stir,
            amount=price,
            awarded_at=created_at,
        )

    # Contract item
    items = []
    item_title = order.get("product_name") or title
    items.append(
        LotItemRecord(
            raw_name=item_title,
            quantity=parse_decimal(raw.get("position_count") or 1),
            unit="dona",
            unit_price_raw=str(price) if price else None,
        )
    )

    return ProcedureRecord(
        source_id=f"ebirja_c_{contract_id or contract_num}",
        source_url=f"https://ebirja.uz/uz/contracts/shop?search={urllib.parse.quote(contract_num)}",
        procedure_type=f"E-Birja {contract_type}",
        title=title,
        status="COMPLETED",
        published_at=created_at,
        deadline_at=created_at,
        completed_at=created_at,
        currency=currency,
        start_price=price,
        customer_name=cust_name,
        customer_stir=cust_stir,
        customer_region=cust_region,
        items=items,
        award=award,
    )


def parse_ebirja_auction(raw: dict[str, Any]) -> ProcedureRecord:
    """Convert raw E-Birja auction dictionary into normalized ProcedureRecord."""
    auction_id = str(raw.get("id") or "")
    lot_num = str(raw.get("lot") or auction_id)
    title = raw.get("title") or f"E-Birja Auksion {lot_num}"

    begin_date = parse_datetime(raw.get("begin_date"))
    end_date = parse_datetime(raw.get("auction_end"))
    total_sum = parse_decimal(raw.get("total_sum") or raw.get("current_price"))

    company = raw.get("company") or {}
    cust_name = company.get("title")
    cust_stir = company.get("tin")
    region_info = raw.get("region") or company.get("region") or {}
    region_name = region_info.get("title_uz") if isinstance(region_info, dict) else None

    items = [
        LotItemRecord(
            raw_name=title,
            quantity=parse_decimal(raw.get("position_count") or 1),
            unit="dona",
            unit_price_raw=str(total_sum) if total_sum else None,
        )
    ]

    return ProcedureRecord(
        source_id=f"ebirja_a_{auction_id or lot_num}",
        source_url=f"https://ebirja.uz/uz/auction/{auction_id}",
        procedure_type="E-Birja Auksion",
        title=title,
        status="ACTIVE",
        published_at=begin_date,
        deadline_at=end_date,
        completed_at=None,
        currency="UZS",
        start_price=total_sum,
        customer_name=cust_name,
        customer_stir=cust_stir,
        customer_region=region_name,
        items=items,
        award=None,
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


def import_ebirja_records(session: Session, records: list[ProcedureRecord]) -> dict[str, int]:
    """Upsert ProcedureRecords from E-Birja with normalization and classification."""
    stats = {"inserted": 0, "updated": 0, "items": 0, "classified_it": 0}

    for rec in records:
        existing = session.scalar(
            select(Procedure).where(
                Procedure.source == "ebirja", Procedure.source_id == rec.source_id
            )
        )

        customer_org = _get_or_create_org(
            session, rec.customer_stir, rec.customer_name, rec.customer_region
        )

        if existing is None:
            proc = Procedure(
                source="ebirja",
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

        # Replace items
        if rec.items:
            existing_items = list(
                session.scalars(select(LotItem).where(LotItem.procedure_id == proc.id))
            )
            for itm in existing_items:
                session.delete(itm)
            session.flush()

            for itm_rec in rec.items:
                norm = normalize_product(itm_rec.raw_name)
                lot_item = LotItem(
                    procedure_id=proc.id,
                    raw_name=itm_rec.raw_name,
                    brand=norm.brand,
                    product_family=norm.product_family,
                    model=norm.model,
                    term_months=norm.term_months,
                    quantity=itm_rec.quantity,
                    unit=itm_rec.unit,
                    unit_price_raw=itm_rec.unit_price_raw,
                )
                session.add(lot_item)
                stats["items"] += 1
            session.flush()

        # Handle Award
        if rec.award and (rec.award.supplier_name or rec.award.amount is not None):
            supp_org = _get_or_create_org(session, rec.award.supplier_stir, rec.award.supplier_name)
            award = session.scalar(select(Award).where(Award.procedure_id == proc.id))
            if not award:
                award = Award(
                    procedure_id=proc.id,
                    supplier_org_id=supp_org.id if supp_org else None,
                    amount=rec.award.amount,
                    awarded_at=rec.award.awarded_at or proc.completed_at,
                )
                session.add(award)
            else:
                award.supplier_org_id = (supp_org.id if supp_org else None) or award.supplier_org_id
                award.amount = rec.award.amount or award.amount
                award.awarded_at = rec.award.awarded_at or award.awarded_at
            session.flush()

        # Classify by rules
        clf = session.scalar(select(Classification).where(Classification.procedure_id == proc.id))
        item_names = [it.raw_name for it in rec.items] or [proc.title]
        text_corpus = build_text(proc.title, item_names)
        rule_result = classify_text(text_corpus)
        is_it = (rule_result.likely_it == "yes")
        confidence = 0.90 if is_it else (0.95 if rule_result.likely_it == "no" else 0.50)

        if not clf:
            clf = Classification(
                procedure_id=proc.id,
                is_it=is_it,
                category=rule_result.category,
                subcategory=None,
                brand=rule_result.brand,
                is_subscription=rule_result.is_subscription,
                term_months=rule_result.term_months,
                method="rule",
                confidence=confidence,
            )
            session.add(clf)
        else:
            clf.is_it = is_it
            clf.category = rule_result.category
            clf.brand = rule_result.brand
            clf.is_subscription = rule_result.is_subscription
            clf.term_months = rule_result.term_months
            clf.confidence = confidence
        session.flush()

        if is_it:
            stats["classified_it"] += 1

    return stats
