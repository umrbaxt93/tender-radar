"""Alerts and notification channels (Telegram, etc.)."""

from __future__ import annotations

from radar.alerts.telegram import (
    TelegramClient,
    format_opportunity_alert,
    send_hot_opportunity_alerts,
)

__all__ = [
    "TelegramClient",
    "format_opportunity_alert",
    "send_hot_opportunity_alerts",
]
