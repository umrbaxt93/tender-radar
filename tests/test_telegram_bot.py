"""Unit tests for interactive Telegram Bot dispatcher and commands."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from radar.alerts.bot import TelegramBotDispatcher
from radar.alerts.telegram import TelegramClient
from radar.config import Settings
from radar.models import (
    Award,
    Base,
    Classification,
    LotItem,
    Organization,
    OrganizationAlias,
    Procedure,
    RenewalOpportunity,
)


def _setup_test_db(engine) -> None:
    tables = [
        Organization.__table__,
        OrganizationAlias.__table__,
        Procedure.__table__,
        LotItem.__table__,
        Award.__table__,
        Classification.__table__,
        RenewalOpportunity.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)


def test_telegram_bot_authorization() -> None:
    settings = Settings(telegram_chat_id="999888")
    client = TelegramClient(bot_token="mock", default_chat_id="999888")
    bot = TelegramBotDispatcher(client, settings)

    assert bot.is_authorized("999888") is True
    assert bot.is_authorized(999888) is True
    assert bot.is_authorized("111222") is False


def test_telegram_bot_unauthorized_rejection() -> None:
    settings = Settings(telegram_chat_id="999888")
    client = TelegramClient(bot_token="mock", default_chat_id="999888")
    bot = TelegramBotDispatcher(client, settings)

    engine = create_engine("sqlite:///:memory:")
    _setup_test_db(engine)

    with Session(engine) as session:
        reply = bot.handle_command("/stats", chat_id="111222", session=session)
        assert "Ruxsat etilmadi" in reply


def test_telegram_bot_commands() -> None:
    settings = Settings(telegram_chat_id="999888")
    client = TelegramClient(bot_token="mock", default_chat_id="999888")
    bot = TelegramBotDispatcher(client, settings)

    engine = create_engine("sqlite:///:memory:")
    _setup_test_db(engine)

    with Session(engine) as session:
        # Seed test data
        cust = Organization(name_canonical="Agrobank ATB", stir="200555666", region="Toshkent")
        supp = Organization(name_canonical="Best IT Solution", stir="305111222")
        session.add_all([cust, supp])
        session.flush()

        proc = Procedure(
            source="uzex",
            source_id="555001",
            title="Cisco tarmoq xavfsizligi tizimi",
            customer_org_id=cust.id,
            start_price=Decimal("120000000"),
        )
        session.add(proc)
        session.flush()

        session.add(Classification(
            procedure_id=proc.id,
            is_it=True,
            category="Tarmoq uskunalari",
            brand="Cisco",
            method="rule",
            confidence=0.95,
        ))
        session.add(Award(
            procedure_id=proc.id,
            supplier_org_id=supp.id,
            amount=Decimal("115000000"),
        ))
        from datetime import UTC, datetime

        session.add(RenewalOpportunity(
            procedure_id=proc.id,
            customer_org_id=cust.id,
            category="Tarmoq uskunalari",
            brand="Cisco",
            score=88,
            amount=Decimal("120000000"),
            lifecycle_months=12,
            computed_at=datetime.now(UTC),
        ))
        session.commit()

        # 1. /help
        help_reply = bot.handle_command("/help", "999888", session)
        assert "SOFTY" in help_reply
        assert "/stats" in help_reply

        # 2. /stats
        stats_reply = bot.handle_command("/stats", "999888", session)
        assert "BOZOR STATISTIKASI" in stats_reply
        assert "1 ta" in stats_reply

        # 3. /hot
        hot_reply = bot.handle_command("/hot", "999888", session)
        assert "Agrobank ATB" in hot_reply
        assert "Cisco" in hot_reply

        # 4. /renewals
        ren_reply = bot.handle_command("/renewals", "999888", session)
        assert "Agrobank ATB" in ren_reply

        # 5. /advisor
        adv_reply = bot.handle_command(f"/advisor {proc.id}", "999888", session)
        assert "AI BIZNES TAVSIYASI" in adv_reply
        assert "Agrobank" in adv_reply

        # 6. /search
        search_reply = bot.handle_command("/search agrobank", "999888", session)
        assert "Agrobank" in search_reply


def test_telegram_bot_chunked_send() -> None:
    sent_messages = []

    class DummyClient(TelegramClient):
        def send_message(self, text: str, **kwargs):
            sent_messages.append(text)
            return {"ok": True}

    client = DummyClient(bot_token="mock", default_chat_id="999888")
    bot = TelegramBotDispatcher(client, Settings())

    # Text larger than 4000 characters
    long_text = "\n".join([f"Qator #{i}: test ma'lumotlari..." for i in range(250)])
    bot._send_reply_chunked(long_text, chat_id="999888")

    assert len(sent_messages) >= 2
