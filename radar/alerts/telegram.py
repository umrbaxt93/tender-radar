"""Telegram Bot alerting module for Renewal Radar opportunities.

Dispatches automated notifications for high-priority ("HOT", score >= 80) opportunities
directly to the configured Telegram recipient (e.g. Umid).
Guarantees idempotency via alert_log table.
"""

from __future__ import annotations

import html
import logging
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.config import Settings
from radar.models import AlertLog, Organization, Procedure, RenewalOpportunity
from radar.privacy import mask_identifier

log = logging.getLogger("radar.alerts.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramClient:
    """HTTP client for Telegram Bot API with mock fallback and retry handling."""

    def __init__(
        self,
        bot_token: str | None = None,
        default_chat_id: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.bot_token = (bot_token or "").strip()
        self.default_chat_id = (default_chat_id or "").strip()
        self._client = client or httpx.Client(timeout=10.0)

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and (self.default_chat_id or self.bot_token != "mock"))

    def send_message(
        self,
        text: str,
        chat_id: str | None = None,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = False,
    ) -> dict[str, Any]:
        """Send a message via Telegram Bot API or mock log if unconfigured."""
        target_chat_id = (chat_id or self.default_chat_id or "").strip()

        if not self.bot_token or self.bot_token == "mock" or not target_chat_id:
            log.info(
                "[MOCK TELEGRAM] Recipient: %s\n%s",
                target_chat_id or "unspecified",
                text,
            )
            return {
                "ok": True,
                "mock": True,
                "result": {"message_id": 999999, "chat": {"id": target_chat_id}},
            }

        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": target_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }

        # Attempt sending with backoff for rate limits (429)
        for attempt in range(3):
            try:
                resp = self._client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data
                elif resp.status_code == 429:
                    retry_after = 1
                    try:
                        retry_after = int(resp.json().get("parameters", {}).get("retry_after", 1))
                    except Exception:
                        pass
                    log.warning("Telegram rate-limited (429). Waiting %ds...", retry_after)
                    time.sleep(retry_after)
                    continue
                else:
                    log.error(
                        "Telegram API error (%d): %s",
                        resp.status_code,
                        resp.text,
                    )
                    return {"ok": False, "error_code": resp.status_code, "description": resp.text}
            except httpx.HTTPError as exc:
                log.error(
                    "Network error sending Telegram message (attempt %d): %s",
                    attempt + 1,
                    exc,
                )
                time.sleep(0.5)

        return {"ok": False, "description": "Failed after 3 attempts"}


def format_opportunity_alert(
    opp: RenewalOpportunity,
    proc: Procedure,
    org: Organization | None,
    ai_recommendation: str | None = None,
) -> str:
    """Format a rich HTML alert message for Telegram."""
    cust_name = html.escape(org.name_canonical if org else "Noma'lum buyurtmachi")
    # For Telegram alerts, show masked PINFL if 14 digits, full STIR if 9 digits
    raw_stir = org.stir if org else None
    masked_stir = mask_identifier(raw_stir, is_admin=False) if raw_stir else "Noma'lum"
    region = html.escape(org.region if org and org.region else "O'zbekiston")

    category = html.escape(opp.category or "IT Xarid")
    brand = html.escape(opp.brand or "Ko'rsatilmagan")

    amount_num = float(proc.start_price or 0)
    amount_str = f"{amount_num:,.0f} so'm".replace(",", " ") if amount_num else "Mavjud emas"

    last_purchase = (
        opp.last_purchase_at.strftime("%Y-%m-%d") if opp.last_purchase_at else "Noma'lum"
    )
    expected_renewal = (
        opp.expected_renewal_at.strftime("%Y-%m-%d") if opp.expected_renewal_at else "Yaqin oylarda"
    )
    contact_by = (
        opp.contact_by_at.strftime("%Y-%m-%d") if opp.contact_by_at else "Darhol aloqaga chiqing"
    )

    title = html.escape(proc.title or "")
    url = proc.source_url or ""

    lines = [
        "🎯 <b>YANGI RENEWAL RADAR IMKONIYATI (HOT)</b> 🎯",
        "",
        f"🏢 <b>Mijoz:</b> {cust_name}",
        f"🔢 <b>STIR:</b> <code>{masked_stir}</code>",
        f"📍 <b>Hudud:</b> {region}",
        "",
        f"📦 <b>Toifa:</b> {category}",
        f"🏷 <b>Brend:</b> {brand}",
        f"💰 <b>Xarid summasi:</b> {amount_str}",
        "",
        f"📅 <b>Oxirgi xarid:</b> {last_purchase}",
        f"⏳ <b>Kutilayotgan yangilash:</b> {expected_renewal}",
        f"🚨 <b>Bog'lanish tavsiya muddati:</b> <b>{contact_by}</b>",
        f"🔥 <b>Radar skori:</b> <b>{opp.score} / 100</b> (HOT)",
        "",
        f"📋 <b>Lot nomi:</b> {title}",
    ]

    if url:
        lines.append(f'🔗 <a href="{url}">Tender / Shartnoma havolasi</a>')

    if ai_recommendation:
        clean_rec = html.escape(ai_recommendation.strip()[:300])
        lines.extend(["", f"🤖 <b>AI Tavsiya:</b> <i>{clean_rec}</i>"])

    return "\n".join(lines)


def send_hot_opportunity_alerts(
    session: Session,
    settings: Settings,
    min_score: int | None = None,
    limit: int = 20,
    dry_run: bool = False,
    client: TelegramClient | None = None,
) -> dict[str, Any]:
    """Find unalerted HOT opportunities and send notifications to Umid's Telegram.

    Idempotent: skips opportunities already recorded in alert_log for Telegram and recipient.
    """
    threshold = min_score if min_score is not None else settings.telegram_alert_min_score
    recipient = (settings.telegram_chat_id or "umid").strip()

    tg_client = client or TelegramClient(
        bot_token=settings.telegram_bot_token,
        default_chat_id=settings.telegram_chat_id,
    )

    # Subquery: procedures already alerted to this recipient via telegram
    alerted_subq = (
        select(AlertLog.procedure_id)
        .where(
            AlertLog.channel == "telegram",
            AlertLog.recipient == recipient,
        )
        .scalar_subquery()
    )

    # Query unalerted opportunities with score >= threshold
    stmt = (
        select(RenewalOpportunity, Procedure, Organization)
        .join(Procedure, Procedure.id == RenewalOpportunity.procedure_id)
        .outerjoin(Organization, Organization.id == RenewalOpportunity.customer_org_id)
        .where(
            RenewalOpportunity.score >= threshold,
            RenewalOpportunity.procedure_id.not_in(alerted_subq),
        )
        .order_by(
            RenewalOpportunity.score.desc(),
            RenewalOpportunity.contact_by_at.asc().nullslast(),
        )
        .limit(limit)
    )

    candidates = session.execute(stmt).all()
    sent_count = 0
    errors_count = 0

    for opp, proc, org in candidates:
        msg = format_opportunity_alert(opp, proc, org)

        if dry_run:
            log.info("[DRY-RUN ALERT] Would send to %s:\n%s", recipient, msg)
            sent_count += 1
            continue

        res = tg_client.send_message(text=msg, chat_id=recipient)
        if res.get("ok"):
            status = "mock" if res.get("mock") else "sent"
            log_entry = AlertLog(
                procedure_id=opp.procedure_id,
                channel="telegram",
                recipient=recipient,
                score=opp.score,
                status=status,
                message_preview=msg[:250],
            )
            session.add(log_entry)
            session.commit()
            sent_count += 1
        else:
            errors_count += 1
            log.error(
                "Failed to send Telegram alert for procedure %d: %s",
                opp.procedure_id,
                res.get("description"),
            )

    log.info(
        "Telegram alerts: found=%d sent=%d errors=%d (recipient=%s, min_score=%d)",
        len(candidates),
        sent_count,
        errors_count,
        recipient,
        threshold,
    )

    return {
        "considered": len(candidates),
        "sent": sent_count,
        "errors": errors_count,
        "recipient": recipient,
        "min_score": threshold,
        "dry_run": dry_run,
    }


def get_telegram_client(settings: Settings | None = None) -> TelegramClient:
    """Create a TelegramClient from system settings."""
    cfg = settings or Settings()
    return TelegramClient(
        bot_token=cfg.telegram_bot_token,
        default_chat_id=cfg.telegram_chat_id,
    )

