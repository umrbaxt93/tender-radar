"""Durable cross-run AI cost ledger enforcing the $10 classifier cap.

Every batch reserves its estimated cost *before* the API call and commits that reservation,
so a crash mid-call can never hide spend. The reservation is settled with real token usage
afterwards. Budget used = sum(actual_usd, falling back to estimated_usd) over rows that did
not fail. This is the control DECISIONS.md requires; it is independent of agent spend.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.models import AiCostLedger

log = logging.getLogger(__name__)
PRICING_PATH = Path(__file__).with_name("pricing.yaml")
CENT = Decimal("0.000001")


class BudgetExceeded(RuntimeError):
    """Raised instead of making a call that would cross the configured cap."""


class PricingUnavailable(RuntimeError):
    """Raised when the configured model has no reviewed price. Never guess one."""


@dataclass(frozen=True)
class Pricing:
    model_name: str
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        million = Decimal(1_000_000)
        total = (Decimal(input_tokens) / million * self.input_usd_per_mtok
                 + Decimal(output_tokens) / million * self.output_usd_per_mtok)
        return total.quantize(CENT, rounding=ROUND_HALF_UP)


@lru_cache(maxsize=1)
def _pricing_file(path: Path = PRICING_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_pricing(model_name: str) -> Pricing:
    """Environment override first, then the reviewed pricing file. Never a guess."""
    env_in = os.environ.get("GEMINI_INPUT_USD_PER_MTOK", "").strip()
    env_out = os.environ.get("GEMINI_OUTPUT_USD_PER_MTOK", "").strip()
    if env_in and env_out:
        return Pricing(model_name, Decimal(env_in), Decimal(env_out))
    entry = (_pricing_file().get("models") or {}).get(model_name)
    if not entry:
        raise PricingUnavailable(
            f"no reviewed price for model {model_name!r}. Add it to "
            f"{PRICING_PATH.name} with the figures from the official pricing page, or set "
            "GEMINI_INPUT_USD_PER_MTOK and GEMINI_OUTPUT_USD_PER_MTOK. Prices are never "
            "guessed, so paid classification will not start without one of these."
        )
    return Pricing(model_name, Decimal(str(entry["input_usd_per_mtok"])),
                   Decimal(str(entry["output_usd_per_mtok"])))


def batch_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CostLedger:
    def __init__(self, session: Session, cap_usd: float | Decimal, pricing: Pricing) -> None:
        self.session = session
        self.cap = Decimal(str(cap_usd))
        self.pricing = pricing

    def spent(self) -> Decimal:
        total = self.session.scalar(
            select(func.coalesce(
                func.sum(func.coalesce(AiCostLedger.actual_usd, AiCostLedger.estimated_usd)),
                0)).where(AiCostLedger.status != "failed")
        )
        return Decimal(str(total or 0))

    def remaining(self) -> Decimal:
        return self.cap - self.spent()

    def reserve(self, payload: str, input_tokens: int, output_tokens: int) -> AiCostLedger:
        """Commit a reservation, or raise BudgetExceeded without calling the model."""
        estimate = self.pricing.cost(input_tokens, output_tokens)
        spent = self.spent()
        if spent + estimate > self.cap:
            raise BudgetExceeded(
                f"batch would cost ~${estimate} on top of ${spent} already recorded, "
                f"crossing the ${self.cap} cap. No API call was made."
            )
        row = AiCostLedger(model_name=self.pricing.model_name, batch_hash=batch_hash(payload),
                           estimated_usd=estimate, settled=False, status="reserved")
        self.session.add(row)
        self.session.commit()
        log.info("reserved $%s for %s (spent $%s of $%s)", estimate,
                 self.pricing.model_name, spent, self.cap)
        return row

    def settle(self, row: AiCostLedger, input_tokens: int, output_tokens: int) -> Decimal:
        actual = self.pricing.cost(input_tokens, output_tokens)
        row.input_tokens = input_tokens
        row.output_tokens = output_tokens
        row.actual_usd = actual
        row.settled = True
        row.status = "settled"
        self.session.commit()
        return actual

    def fail(self, row: AiCostLedger) -> None:
        """A call that produced nothing usable is not charged against the cap."""
        row.status = "failed"
        row.settled = True
        row.actual_usd = Decimal("0")
        self.session.commit()
