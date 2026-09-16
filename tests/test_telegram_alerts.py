"""Tests for automated Telegram alert notifications for HOT renewal opportunities."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import httpx

from radar.alerts.telegram import (
    TelegramClient,
    format_opportunity_alert,
    send_hot_opportunity_alerts,
)
from radar.config import Settings
from radar.db import session_scope
from radar.models import (
    AlertLog,
    Classification,
    Organization,
    Procedure,
    RenewalOpportunity,
)


def test_telegram_client_mock_mode():
    """Verify TelegramClient operates safely in mock mode when unconfigured."""
    client = TelegramClient(bot_token="", default_chat_id="")
    assert not client.is_configured

    res = client.send_message("Test message", chat_id="umid_test")
    assert res["ok"] is True
    assert res["mock"] is True


def test_telegram_client_mock_transport():
    """Verify TelegramClient sends correct JSON payload to Telegram API."""
    captured_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/bot123456:ABC-DEF/sendMessage"
        import json

        data = json.loads(request.read())
        captured_payloads.append(data)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)

    client = TelegramClient(
        bot_token="123456:ABC-DEF",
        default_chat_id="umid_telegram_id",
        client=http_client,
    )
    assert client.is_configured

    res = client.send_message("<b>Salom Umid!</b>")
    assert res["ok"] is True
    assert res["result"]["message_id"] == 42
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["chat_id"] == "umid_telegram_id"
    assert captured_payloads[0]["parse_mode"] == "HTML"
    assert "Salom Umid" in captured_payloads[0]["text"]


def test_format_opportunity_alert():
    """Verify HTML formatting of renewal opportunity alert message."""
    org = Organization(stir="308904387", name_canonical="O'zbekinvest Sug'urta Kompaniyasi")
    proc = Procedure(
        source="uzex",
        source_id="proc_test_alert",
        title="Check Point Security Gateway Litsenziyasi <2026>",
        start_price=120_000_000.0,
        source_url="https://xarid.uzex.uz/detail/123",
    )
    opp = RenewalOpportunity(
        category="FIREWALL",
        brand="Check Point",
        score=92,
        last_purchase_at=datetime(2025, 10, 1, tzinfo=UTC),
        expected_renewal_at=datetime(2026, 10, 1, tzinfo=UTC),
        contact_by_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    msg = format_opportunity_alert(
        opp, proc, org, ai_recommendation="5% chegirma va bepul konsultatsiya taklif qiling"
    )

    assert "YANGI RENEWAL RADAR IMKONIYATI (HOT)" in msg
    assert "O&#x27;zbekinvest" in msg or "O'zbekinvest" in msg
    assert "<code>308904387</code>" in msg
    assert "Check Point" in msg
    assert "92 / 100" in msg
    assert "120 000 000 so'm" in msg
    assert "https://xarid.uzex.uz/detail/123" in msg
    assert "bepul konsultatsiya" in msg


def test_send_hot_opportunity_alerts_idempotent():
    """Verify send_hot_opportunity_alerts dispatches alerts and prevents duplicate deliveries."""
    test_stir = f"99{int.from_bytes(os.urandom(4), 'big') % 10**7:07d}"
    recipient = "umid_unique_test"

    with session_scope() as session:
        org = Organization(stir=test_stir, name_canonical="Umid Alert Test Org")
        session.add(org)
        session.flush()

        proc = Procedure(
            source="uzex",
            source_id=f"hot_{os.urandom(3).hex()}",
            title="Fortinet FortiGate Renewal Test",
            customer_org_id=org.id,
            start_price=85_000_000.0,
            completed_at=datetime.now(UTC) - timedelta(days=330),
        )
        session.add(proc)
        session.flush()

        cls = Classification(
            procedure_id=proc.id,
            is_it=True,
            confidence=0.98,
            category="FIREWALL",
            brand="Fortinet",
            method="rule",
        )
        session.add(cls)

        opp = RenewalOpportunity(
            procedure_id=proc.id,
            customer_org_id=org.id,
            category="FIREWALL",
            brand="Fortinet",
            lifecycle_months=12,
            last_purchase_at=datetime.now(UTC) - timedelta(days=330),
            expected_renewal_at=datetime.now(UTC) + timedelta(days=35),
            contact_by_at=datetime.now(UTC) - timedelta(days=5),
            score=99,  # Isolated HOT score >= 99 to prevent DB crosstalk
            computed_at=datetime.now(UTC),
        )
        session.add(opp)
        session.commit()
        proc_id = proc.id

    mock_client = TelegramClient(bot_token="mock", default_chat_id=recipient)
    settings = Settings(
        telegram_bot_token="mock",
        telegram_chat_id=recipient,
        telegram_alert_min_score=99,
    )

    try:
        # First dispatch: should find 1 candidate and send
        with session_scope() as session:
            stats1 = send_hot_opportunity_alerts(
                session=session,
                settings=settings,
                min_score=99,
                client=mock_client,
            )
            assert stats1["considered"] == 1
            assert stats1["sent"] == 1
            assert stats1["errors"] == 0

        # Verify AlertLog row created
        with session_scope() as session:
            entry = (
                session.query(AlertLog)
                .filter_by(procedure_id=proc_id, recipient=recipient, channel="telegram")
                .first()
            )
            assert entry is not None
            assert entry.score == 99
            assert entry.status == "mock"

        # Second dispatch (idempotency check): should find 0 unalerted candidates for this procedure
        with session_scope() as session:
            stats2 = send_hot_opportunity_alerts(
                session=session,
                settings=settings,
                min_score=99,
                client=mock_client,
            )
            assert stats2["sent"] == 0
            # The newly created proc_id must NOT be sent again
            already_alerted = (
                session.query(AlertLog).filter_by(procedure_id=proc_id, recipient=recipient).count()
            )
            assert already_alerted == 1

    finally:
        with session_scope() as session:
            session.query(AlertLog).filter_by(procedure_id=proc_id).delete()
            session.query(RenewalOpportunity).filter_by(procedure_id=proc_id).delete()
            session.query(Classification).filter_by(procedure_id=proc_id).delete()
            p = session.get(Procedure, proc_id)
            if p:
                session.delete(p)
            o = session.query(Organization).filter_by(stir=test_stir).first()
            if o:
                session.delete(o)
            session.commit()


def test_cli_alert_dry_run():
    """Verify python -m radar alert --dry-run CLI command runs successfully."""
    from radar.cli import main

    code = main(["alert", "--dry-run", "--min-score", "90"])
    assert code == 0


def test_worker_dispatch_alerts():
    """Verify worker.dispatch_alerts executes without raising errors."""
    from radar.worker import dispatch_alerts

    res = dispatch_alerts()
    assert isinstance(res, dict)
    assert "sent" in res
    assert "errors" in res
