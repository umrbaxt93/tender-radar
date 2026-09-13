"""Rules classifier against the labelled golden set in samples/synthetic/known_lots.md."""

from __future__ import annotations

import pytest

from radar.classify.rules import CATEGORIES, classify_procedure, detect_term_months, normalize
from radar.config import ROOT

GOLDEN = ROOT / "samples" / "synthetic" / "known_lots.md"


def load_golden() -> list[dict[str, str]]:
    rows = []
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| G-"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(dict(zip(["id", "title", "items", "expected_it", "category", "must_decide"],
                             cells, strict=True)))
    return rows


GOLDEN_ROWS = load_golden()


def test_golden_set_is_loadable_and_balanced():
    assert len(GOLDEN_ROWS) >= 20
    it = [r for r in GOLDEN_ROWS if r["expected_it"] == "yes"]
    non_it = [r for r in GOLDEN_ROWS if r["expected_it"] == "no"]
    assert len(it) >= 5 and len(non_it) >= 5


@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=[r["id"] for r in GOLDEN_ROWS])
def test_rules_never_contradict_the_golden_label(row):
    """The rules layer may abstain, but it must never decide the wrong way."""
    result = classify_procedure(row["title"], [row["items"]])
    if result.likely_it == "yes":
        assert row["expected_it"] == "yes", f"{row['id']}: non-IT lot classified as IT"
    if result.likely_it == "no":
        assert row["expected_it"] == "no", f"{row['id']}: IT lot classified as non-IT"


@pytest.mark.parametrize("row", [r for r in GOLDEN_ROWS if r["must_decide"] == "yes"],
                         ids=[r["id"] for r in GOLDEN_ROWS if r["must_decide"] == "yes"])
def test_rules_decide_the_clear_cases_without_ai(row):
    result = classify_procedure(row["title"], [row["items"]])
    assert result.decided, f"{row['id']}: rules abstained on a clear case, wasting an AI call"
    if result.likely_it == "yes" and row["category"]:
        assert result.category == row["category"], f"{row['id']}: wrong category"


def test_ambiguous_rows_are_left_to_the_ai():
    for row in GOLDEN_ROWS:
        if row["must_decide"] == "no":
            result = classify_procedure(row["title"], [row["items"]])
            assert result.likely_it == "unsure", f"{row['id']}: should stay unsure"


def test_every_configured_category_is_known():
    for row in GOLDEN_ROWS:
        result = classify_procedure(row["title"], [row["items"]])
        assert result.category is None or result.category in CATEGORIES


def test_subscription_and_term_detection():
    result = classify_procedure("Microsoft 365 obunasi 1 yil", ["Microsoft 365 Business"])
    assert result.is_subscription and result.term_months == 12
    result = classify_procedure("Server xarid qilish", ["HPE ProLiant"])
    assert not result.is_subscription and result.term_months is None
    assert detect_term_months(normalize("продление на 36 месяцев")) == 36
    assert detect_term_months(normalize("srok 3 yil")) == 36
    assert detect_term_months(normalize("kafolat 500 oy")) is None


def test_brand_detection():
    assert classify_procedure("FortiGate FG-100F", []).brand == "Fortinet"
    assert classify_procedure("Ноутбук ThinkPad", []).brand == "Lenovo"
    assert classify_procedure("Stol va stul", []).brand is None


def test_normalization_handles_apostrophes_and_yo():
    assert normalize("Yoqilg‘i") == normalize("Yoqilg'i")
    assert normalize("ЁЖ") == "еж"
