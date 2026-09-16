"""Interactive Telegram Bot daemon and command dispatcher for Tender Radar.

Enables Umidjon to interact with the AI Business Advisor, inspect HOT renewals,
query market statistics, and search government procurement records directly
from Telegram with strict authentication.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from radar.ai_advisor import (
    compute_macro_metrics,
    format_lot_recommendation,
    format_macro_strategy,
    generate_macro_business_strategy,
    get_recommendation_for_procedure,
)
from radar.alerts.telegram import TelegramClient
from radar.config import Settings
from radar.db import session_scope
from radar.models import Classification, Organization, Procedure, RenewalOpportunity

log = logging.getLogger("radar.alerts.bot")


class TelegramBotDispatcher:
    """Dispatches incoming Telegram bot commands to radar analytical services."""

    def __init__(self, client: TelegramClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.last_update_id = 0

    def is_authorized(self, chat_id: str | int) -> bool:
        """Check if incoming chat_id is the configured owner (Umidjon)."""
        expected = (self.settings.telegram_chat_id or "").strip()
        if not expected or expected == "mock":
            # In mock or unconfigured mode, allow local testing
            return True
        return str(chat_id).strip() == expected

    def handle_command(
        self,
        command_text: str,
        chat_id: str | int,
        session: Session,
    ) -> str:
        """Parse command and return markdown formatted response."""
        text = (command_text or "").strip()
        if not text.startswith("/"):
            text = f"/{text}"

        parts = text.split()
        raw_cmd = parts[0].lower().split("@")[0]  # Remove bot username if present
        args = parts[1:]

        if not self.is_authorized(chat_id):
            log.warning("Unauthorized access attempt to bot from chat_id=%s", chat_id)
            return (
                "⚠️ *Ruxsat etilmadi*\n"
                "Ushbu bot faqat SOFTY LLC rahbariyati (Umidjon) uchun mo'ljallangan.\n"
                f"Sizning Chat ID: `{chat_id}`"
            )

        if raw_cmd in ("/start", "/help"):
            return self._cmd_help()
        elif raw_cmd == "/stats":
            return self._cmd_stats(session)
        elif raw_cmd == "/hot":
            return self._cmd_hot(session)
        elif raw_cmd in ("/macro", "/strategy"):
            return self._cmd_macro(session)
        elif raw_cmd == "/renewals":
            return self._cmd_renewals(session)
        elif raw_cmd == "/advisor":
            return self._cmd_advisor(session, args)
        elif raw_cmd == "/search":
            return self._cmd_search(session, args)
        elif raw_cmd == "/alert":
            return self._cmd_alert(session)
        else:
            return (
                f"❓ Noma'lum buyruq: `{raw_cmd}`\n\n"
                "Mavjud buyruqlarni ko'rish uchun /help ni bosing."
            )

    def _cmd_help(self) -> str:
        return (
            "👋 *Assalomu alaykum, Umidjon!*\n"
            "\"SOFTY\" Tender Radar — Sun'iy Intellekt B2B Maslahatchi botiga xush kelibsiz.\n\n"
            "📌 *Mavjud buyruqlar:*\n"
            "📊 /stats — Xaridlar bazasi va IT bozor statistikasi\n"
            "🔥 /hot — Eng yuqori balli (HOT, score >= 80) yangilanishlar\n"
            "🎯 /macro — Softy LLC uchun bozor tahlili va biznes strategiyasi\n"
            "📅 /renewals — Muddati kelayotgan litsenziyalar taqvimi\n"
            "💡 /advisor [lot_id] — AI tahlil, chegirma va tijoriy taklif\n"
            "🔎 /search <matn> — Buyurtmachi yoki tovar bo'yicha qidiruv\n"
            "⚡ /alert — Yangi HOT imkoniyatlar monitoringini yuborish\n\n"
            "Barcha ma'lumotlar real davlat xaridlari (UZEX, E-Birja) bilan sinxronlashgan."
        )

    def _cmd_stats(self, session: Session) -> str:
        metrics = compute_macro_metrics(session)
        it_vol = metrics.get("it_volume_uzs", 0)
        it_pct = metrics.get('it_share_pct', 0)
        hot_cnt = metrics.get('hot_renewals', 0)
        return (
            "📊 *TENDER RADAR — BOZOR STATISTIKASI*\n\n"
            f"• Jami xaridlar: *{metrics.get('total_procedures', 0):,} ta*\n"
            f"• IT xaridlari: *{metrics.get('it_procedures', 0):,} ta* ({it_pct}%)\n"
            f"• IT bozor umumiy qiymati: *{it_vol:,.0f} UZS*\n"
            f"• Tashkilotlar soni: *{len(metrics.get('top_buyers', [])) * 10}+ ta*\n"
            f"• Jami yangilanish (Renewal) imkoniyatlari: *{metrics.get('total_renewals', 0)} ta*\n"
            f"• Shundan zudlik bilan chiqish kerak bo'lgan HOT (>=80): *{hot_cnt} ta*\n\n"
            "💡 _Batafsil strategiya uchun /macro buyrug'ini bering._"
        )

    def _cmd_hot(self, session: Session) -> str:
        rows = session.execute(
            select(
                RenewalOpportunity.id,
                RenewalOpportunity.score,
                RenewalOpportunity.contact_by_at,
                RenewalOpportunity.expected_renewal_at,
                Procedure.id.label("proc_id"),
                Procedure.source,
                Procedure.source_id,
                Procedure.title,
                Procedure.start_price,
                Organization.name_canonical.label("cust_name"),
                Organization.region.label("cust_region"),
                Classification.brand,
            )
            .join(Procedure, Procedure.id == RenewalOpportunity.procedure_id)
            .outerjoin(Organization, Organization.id == Procedure.customer_org_id)
            .outerjoin(Classification, Classification.procedure_id == Procedure.id)
            .where(RenewalOpportunity.score >= 80)
            .order_by(desc(RenewalOpportunity.score))
            .limit(5)
        ).all()

        if not rows:
            return "🔥 Hozircha yangi HOT imkoniyatlar (score >= 80) mavjud emas."

        lines = ["🔥 *ENG YUQORI USTUVORLIKDAGI (HOT) YANGILANISHLAR:*", ""]
        for idx, r in enumerate(rows, 1):
            amount = float(r[8] or 0)
            exp_date = r[3].strftime("%Y-%m-%d") if r[3] else "Yaqin kunlarda"
            lines.extend([
                f"*{idx}. {r[9] or 'Nomaʼlum mijoz'}*",
                f"   🏷 Lot: #{r[6]} — {r[7][:45]}...",
                f"   💵 Summa: *{amount:,.0f} UZS* | Brend: *{r[11] or 'IT'}*",
                f"   📅 Kutilayotgan yangilanish: *{exp_date}* (Ball: *{r[1]}*)",
                f"   👉 AI tahlil: `/advisor {r[4]}`",
                "",
            ])
        lines.append("Batafsil tavsiya va tijoriy taklif uchun `/advisor <id>` ni bosing.")
        return "\n".join(lines)

    def _cmd_renewals(self, session: Session) -> str:
        rows = session.execute(
            select(
                RenewalOpportunity.score,
                RenewalOpportunity.expected_renewal_at,
                Procedure.id.label("proc_id"),
                Procedure.source_id,
                Organization.name_canonical.label("cust_name"),
                Procedure.start_price,
                Classification.brand,
            )
            .join(Procedure, Procedure.id == RenewalOpportunity.procedure_id)
            .outerjoin(Organization, Organization.id == Procedure.customer_org_id)
            .outerjoin(Classification, Classification.procedure_id == Procedure.id)
            .order_by(RenewalOpportunity.expected_renewal_at.asc().nullslast())
            .limit(8)
        ).all()

        if not rows:
            return "📅 Yangilanish imkoniyatlari topilmadi."

        lines = ["📅 *YAQIN KUNLARDA KUTILAYOTGAN LITSENZIYA YANGILANISHLARI:*", ""]
        for r in rows:
            date_str = r[1].strftime("%Y-%m-%d") if r[1] else "Noaniq"
            amount = float(r[5] or 0)
            lines.append(
                f"• *{date_str}* — {r[4] or 'Mijoz'}\n"
                f"  Summa: *{amount:,.0f} UZS* | Brend: *{r[6] or '-'}* (Ball: {r[0]})\n"
                f"  Tahlil: `/advisor {r[2]}`\n"
            )
        return "\n".join(lines)

    def _cmd_macro(self, session: Session) -> str:
        strat = generate_macro_business_strategy(session)
        return format_macro_strategy(strat)

    def _cmd_advisor(self, session: Session, args: list[str]) -> str:
        proc_id: int | None = None
        if args:
            raw_arg = args[0].strip()
            # Check if arg is numeric procedure_id
            if raw_arg.isdigit():
                candidate = session.get(Procedure, int(raw_arg))
                if candidate:
                    proc_id = candidate.id
                else:
                    # Try finding by source_id
                    candidate = session.scalar(
                        select(Procedure).where(Procedure.source_id == raw_arg)
                    )
                    if candidate:
                        proc_id = candidate.id

        if not proc_id:
            # Pick highest score opportunity
            top_opp = session.scalar(
                select(RenewalOpportunity.procedure_id).order_by(desc(RenewalOpportunity.score))
            )
            proc_id = top_opp

        if not proc_id:
            return "❌ Tavsiya berish uchun tizimda lot topilmadi."

        rec = get_recommendation_for_procedure(session, proc_id)
        if "error" in rec:
            return f"❌ Xatolik: {rec['error']}"

        return format_lot_recommendation(rec)

    def _cmd_search(self, session: Session, args: list[str]) -> str:
        if not args:
            return (
                "🔎 Qidiruv uchun so'z kiriting. Masalan:\n"
                "`/search microsoft` yoki `/search bank`"
            )

        query_str = " ".join(args).strip()
        pattern = f"%{query_str}%"

        rows = session.execute(
            select(
                Procedure.id,
                Procedure.source,
                Procedure.source_id,
                Procedure.title,
                Procedure.start_price,
                Procedure.status,
                Organization.name_canonical.label("cust_name"),
            )
            .outerjoin(Organization, Organization.id == Procedure.customer_org_id)
            .where(
                or_(
                    Procedure.title.ilike(pattern),
                    Organization.name_canonical.ilike(pattern),
                    Procedure.source_id.ilike(pattern),
                )
            )
            .order_by(desc(Procedure.id))
            .limit(5)
        ).all()

        if not rows:
            return f"🔍 '{query_str}' bo'yicha hech narsa topilmadi."

        lines = [f"🔍 *'{query_str}' BO'YICHA QIDIRUV NATIJALARI:*", ""]
        for r in rows:
            amount = float(r[4] or 0)
            lines.extend([
                f"• *{r[6] or 'Nomaʼlum mijoz'}*",
                f"  Lot: #{r[2]} ({r[1]}) — {r[3][:45]}...",
                f"  Summa: *{amount:,.0f} UZS* | Holati: {r[5]}",
                f"  Tahlil: `/advisor {r[0]}`",
                "",
            ])
        return "\n".join(lines)

    def _cmd_alert(self, session: Session) -> str:
        from radar.alerts.telegram import dispatch_alerts

        stats = dispatch_alerts(session, self.settings, min_score=80)
        disp = stats.get("dispatched", 0)
        skip = stats.get("skipped_existing", 0)
        return (
            "⚡ *YANGI IMKONIYaTLAR MONITORINGI YAKUNLANDI*\n\n"
            f"• Ko'rib chiqildi: *{stats.get('considered', 0)} ta*\n"
            f"• Yangi yuborilgan xabarnomalar: *{disp} ta*\n"
            f"• Qayta yuborishdan saqlanganlar (idempotent): *{skip} ta*\n"
            f"• Xatoliklar: *{stats.get('failed', 0)} ta*"
        )

    def poll_once(self) -> int:
        """Poll Telegram getUpdates once and dispatch messages."""
        if not self.client.bot_token or self.client.bot_token == "mock":
            log.debug("Telegram client is in mock mode; skipping real polling.")
            return 0

        url = f"https://api.telegram.org/bot{self.client.bot_token}/getUpdates"
        params = {"timeout": 10}
        if self.last_update_id:
            params["offset"] = self.last_update_id + 1

        try:
            resp = self.client._client.get(url, params=params, timeout=15.0)
            if resp.status_code != 200:
                log.warning("Telegram getUpdates returned %d: %s", resp.status_code, resp.text)
                return 0

            data = resp.json()
            updates = data.get("result", [])
            processed = 0

            for upd in updates:
                upd_id = upd.get("update_id", 0)
                if upd_id > self.last_update_id:
                    self.last_update_id = upd_id

                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                text = msg.get("text", "")

                if not chat_id or not text:
                    continue

                log.info("Received bot command '%s' from chat_id=%s", text, chat_id)
                with session_scope() as session:
                    reply_text = self.handle_command(text, chat_id, session)

                # Send reply (chunked if longer than 4000 characters)
                self._send_reply_chunked(reply_text, chat_id)
                processed += 1

            return processed
        except Exception as exc:
            log.warning("Error during Telegram polling: %s", exc)
            return 0

    def _send_reply_chunked(self, text: str, chat_id: str | int) -> None:
        """Send message in chunks if it exceeds Telegram's 4096 character limit."""
        max_len = 4000
        if len(text) <= max_len:
            self.client.send_message(text, chat_id=str(chat_id), parse_mode="Markdown")
            return

        chunks = []
        current = []
        cur_len = 0
        for line in text.split("\n"):
            if cur_len + len(line) + 1 > max_len:
                chunks.append("\n".join(current))
                current = [line]
                cur_len = len(line)
            else:
                current.append(line)
                cur_len += len(line) + 1
        if current:
            chunks.append("\n".join(current))

        for chunk in chunks:
            self.client.send_message(chunk, chat_id=str(chat_id), parse_mode="Markdown")
            time.sleep(0.3)

    def run_forever(self, interval_s: float = 2.0) -> None:
        """Continuously poll Telegram updates until interrupted."""
        log.info(
            "Starting Tender Radar Telegram Bot listener for authorized chat: %s",
            self.settings.telegram_chat_id or "unconfigured (mock)",
        )
        try:
            while True:
                self.poll_once()
                time.sleep(interval_s)
        except KeyboardInterrupt:
            log.info("Telegram bot listener stopped by user.")
