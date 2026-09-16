"""Runtime configuration read from environment variables (never from committed files)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env_file() -> None:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    contact_email: str = field(default_factory=lambda: _env("CONTACT_EMAIL"))
    # Softy's own STIR, used as the identity for E-IMZO sessions against E-Birja.
    company_tin: str = field(default_factory=lambda: _env("COMPANY_TIN"))
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
    # Trigram similarity above which two customer names are treated as the same
    # organization when neither side carries a STIR. Deliberately strict: merging two
    # real organizations is far worse than keeping a duplicate.
    org_match_threshold: float = field(default_factory=lambda: _float("ORG_MATCH_THRESHOLD", 0.92))
    request_interval_s: float = field(default_factory=lambda: _float("REQUEST_INTERVAL_S", 3.0))
    out_dir: Path = field(default_factory=lambda: ROOT / _env("OUT_DIR", "out"))
    # Dashboard build and deploy. All empty by default: the worker skips deployment
    # rather than failing when an operator has not configured a target.
    dashboard_data_path: str = field(default_factory=lambda: _env("DASHBOARD_DATA_PATH"))
    dashboard_build_script: str = field(default_factory=lambda: _env("DASHBOARD_BUILD_SCRIPT"))
    dashboard_html_path: str = field(default_factory=lambda: _env("DASHBOARD_HTML_PATH"))
    deploy_ssh_key: str = field(default_factory=lambda: _env("DEPLOY_SSH_KEY"))
    deploy_ssh_port: str = field(default_factory=lambda: _env("DEPLOY_SSH_PORT", "22"))
    deploy_target: str = field(default_factory=lambda: _env("DEPLOY_TARGET"))
    # Telegram alerts configuration (sends HOT renewal alerts directly to Umid)
    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))
    telegram_alert_min_score: int = field(
        default_factory=lambda: int(_env("TELEGRAM_ALERT_MIN_SCORE", "80"))
    )

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def deploy_configured(self) -> bool:
        return bool(self.dashboard_html_path and self.deploy_ssh_key and self.deploy_target)

    def require_database(self) -> str:
        if not self.database_url:
            raise SystemExit("DATABASE_URL is not set (see .env.example)")
        return self.database_url


def load_settings(load_env: bool = True) -> Settings:
    if load_env:
        _load_env_file()
    return Settings()
