"""Runtime configuration read from environment variables (never from committed files)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    contact_email: str = field(default_factory=lambda: _env("CONTACT_EMAIL"))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL"))
    classifier_budget_usd: float = field(
        default_factory=lambda: _float("CLASSIFIER_BUDGET_USD", 10.0)
    )
    # Source contract. Empty by default: the public UZEX endpoints are UNVERIFIED
    # (see docs/SOURCE_API.md) and must be configured explicitly by the operator.
    source_list_url: str = field(default_factory=lambda: _env("UZEX_LIST_URL"))
    source_detail_url: str = field(default_factory=lambda: _env("UZEX_DETAIL_URL"))
    source_fixture_dir: str = field(default_factory=lambda: _env("SOURCE_FIXTURE_DIR"))
    request_interval_s: float = field(default_factory=lambda: _float("REQUEST_INTERVAL_S", 3.0))
    out_dir: Path = field(default_factory=lambda: ROOT / _env("OUT_DIR", "out"))

    def require_database(self) -> str:
        if not self.database_url:
            raise SystemExit("DATABASE_URL is not set (see .env.example)")
        return self.database_url


def load_settings() -> Settings:
    return Settings()
