"""Cost ledger: the $10 stop must hold across runs and before any call is made."""

from __future__ import annotations

from decimal import Decimal

import pytest

from radar.classify.budget import (
    BudgetExceeded,
    CostLedger,
    Pricing,
    PricingUnavailable,
    load_pricing,
)
from radar.models import AiCostLedger

PRICING = Pricing("mock", Decimal("1.0"), Decimal("4.0"))


def test_cost_arithmetic():
    assert PRICING.cost(1_000_000, 0) == Decimal("1.000000")
    assert PRICING.cost(0, 1_000_000) == Decimal("4.000000")
    assert PRICING.cost(500_000, 250_000) == Decimal("1.500000")


def test_pricing_is_never_guessed():
    with pytest.raises(PricingUnavailable) as exc:
        load_pricing("some-unpriced-model")
    assert "never guessed" in str(exc.value)


def test_pricing_env_override(monkeypatch):
    monkeypatch.setenv("GEMINI_INPUT_USD_PER_MTOK", "0.5")
    monkeypatch.setenv("GEMINI_OUTPUT_USD_PER_MTOK", "2")
    pricing = load_pricing("anything")
    assert pricing.cost(1_000_000, 1_000_000) == Decimal("2.500000")


def test_mock_model_is_priced_so_tests_exercise_the_cap():
    assert load_pricing("mock").input_usd_per_mtok > 0


def test_reserve_then_settle(session):
    ledger = CostLedger(session, 10, PRICING)
    assert ledger.spent() == Decimal("0")
    row = ledger.reserve("payload", 1_000_000, 0)
    assert row.status == "reserved" and not row.settled
    # The reservation is committed, so a crash before settling still counts as spend.
    assert ledger.spent() == Decimal("1.000000")
    ledger.settle(row, 2_000_000, 0)
    assert ledger.spent() == Decimal("2.000000")
    assert session.get(AiCostLedger, row.id).settled is True


def test_failed_call_is_not_charged(session):
    ledger = CostLedger(session, 10, PRICING)
    row = ledger.reserve("payload", 1_000_000, 0)
    ledger.fail(row)
    assert ledger.spent() == Decimal("0")


def test_budget_stop_happens_before_the_call(session):
    ledger = CostLedger(session, 2, PRICING)
    ledger.settle(ledger.reserve("a", 1_500_000, 0), 1_500_000, 0)
    assert ledger.remaining() == Decimal("0.500000")
    with pytest.raises(BudgetExceeded) as exc:
        ledger.reserve("b", 1_000_000, 0)
    assert "No API call was made" in str(exc.value)
    assert ledger.spent() == Decimal("1.500000")


def test_budget_survives_a_new_ledger_instance(session):
    CostLedger(session, 10, PRICING).settle(
        CostLedger(session, 10, PRICING).reserve("a", 9_900_000, 0), 9_900_000, 0)
    fresh = CostLedger(session, 10, PRICING)
    assert fresh.remaining() == Decimal("0.100000")
    with pytest.raises(BudgetExceeded):
        fresh.reserve("b", 200_000, 0)
