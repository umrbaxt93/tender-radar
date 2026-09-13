"""Classification pipeline: rules first, cache second, model last, budget always."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select

from radar.classify import gemini as g
from radar.classify.pipeline import run_classification
from radar.config import Settings
from radar.models import AiCache, AiCostLedger, Classification, LotItem, Procedure

SETTINGS = Settings(database_url="", contact_email="", gemini_api_key="", gemini_model="",
                    classifier_budget_usd=10.0)


def add_lot(session, source_id: str, title: str, item: str) -> int:
    proc = Procedure(source="synthetic", source_id=source_id, title=title)
    session.add(proc)
    session.flush()
    session.add(LotItem(procedure_id=proc.id, raw_name=item))
    session.commit()
    return proc.id


@dataclass
class CountingModel:
    """Wraps the mock model and records how many lots it was asked about."""
    name: str = "mock"
    calls: int = 0
    items_seen: int = 0

    def generate(self, prompt: str, item_count: int) -> g.ModelResponse:
        self.calls += 1
        self.items_seen += item_count
        return g.MockModel().generate(prompt, item_count)


def test_rules_settle_clear_lots_without_any_model(session):
    add_lot(session, "R1", "Kaspersky litsenziyasi 12 oy", "Kaspersky Endpoint Security")
    add_lot(session, "R2", "Ofis mebeli xarid qilish", "Ofis stoli")
    model = CountingModel()
    report = run_classification(session, SETTINGS, model=model)
    assert model.calls == 0
    assert report.by_rule == 2 and report.rule_non_it == 1 and report.by_model == 0
    rows = {c.procedure_id: c for c in session.scalars(select(Classification))}
    assert all(c.method == "rule" for c in rows.values())
    it_rows = [c for c in rows.values() if c.is_it]
    assert len(it_rows) == 1 and it_rows[0].category == "Antivirus/EDR"
    assert it_rows[0].is_subscription and it_rows[0].term_months == 12


def test_ambiguous_lots_reach_the_model_and_are_cached(session):
    pid = add_lot(session, "A1", "Оказание услуг по сопровождению информационной системы",
                  "Сопровождение ИС")
    model = CountingModel()
    report = run_classification(session, SETTINGS, model=model)
    assert model.calls == 1 and report.by_model == 1
    row = session.get(Classification, pid)
    assert row.method == "ai" and row.model_name == "mock"
    assert session.scalar(select(func.count()).select_from(AiCache)) == 1

    # A second run over the same text must not call the model again.
    session.execute(Classification.__table__.delete())
    session.commit()
    again = run_classification(session, SETTINGS, model=model)
    assert model.calls == 1 and again.from_cache == 1 and again.by_model == 0


def test_identical_text_is_deduplicated_within_a_run(session):
    for n in range(5):
        add_lot(session, f"D{n}", "Оказание услуг по сопровождению информационной системы",
                "Сопровождение ИС")
    model = CountingModel()
    report = run_classification(session, SETTINGS, model=model)
    assert model.items_seen == 1, "the same text must be sent once"
    assert report.deduplicated == 4 and report.by_model == 5
    assert session.scalar(select(func.count()).select_from(Classification)) == 5


def test_rules_only_never_calls_the_model(session):
    add_lot(session, "O1", "Оказание услуг по сопровождению информационной системы", "ИС")
    model = CountingModel()
    report = run_classification(session, SETTINGS, use_ai=False, model=model)
    assert model.calls == 0 and "rules_only" in report.stopped_reason


def test_missing_api_key_stops_cleanly(session):
    add_lot(session, "K1", "Оказание услуг по сопровождению информационной системы", "ИС")
    report = run_classification(session, SETTINGS)
    assert report.stopped_reason == "no_gemini_api_key" and report.by_model == 0


def test_budget_stop_prevents_further_batches(session):
    for n in range(6):
        add_lot(session, f"B{n}", f"Оказание услуг по сопровождению системы {n}", f"ИС {n}")
    tiny = Settings(database_url="", contact_email="", gemini_api_key="", gemini_model="",
                    classifier_budget_usd=0.0000005)
    model = CountingModel()
    report = run_classification(session, tiny, model=model, batch_size=2)
    assert model.calls == 0, "no call may be made once the cap is reached"
    assert "budget_exceeded" in report.stopped_reason
    assert session.scalar(select(func.count()).select_from(AiCostLedger)) == 0


def test_model_failure_is_not_charged(session):
    add_lot(session, "F1", "Оказание услуг по сопровождению информационной системы", "ИС")

    class Broken:
        name = "mock"

        def generate(self, prompt, item_count):
            raise RuntimeError("upstream unavailable")

    report = run_classification(session, SETTINGS, model=Broken())
    assert report.by_model == 0 and report.errors
    ledger_row = session.scalar(select(AiCostLedger))
    assert ledger_row.status == "failed" and float(ledger_row.actual_usd) == 0.0


def test_second_run_skips_already_classified_lots(session):
    add_lot(session, "S1", "Server HPE ProLiant xarid qilish", "HPE ProLiant DL380")
    first = run_classification(session, SETTINGS)
    assert first.considered == 1
    second = run_classification(session, SETTINGS)
    assert second.considered == 0 and second.stopped_reason == "nothing_to_do"


def test_model_answers_are_clamped():
    values = g.normalize_result({"is_it": True, "category": "Nonsense", "term_months": 999,
                                 "confidence": 5})
    assert values["category"] == "Other IT"
    assert values["term_months"] is None and values["confidence"] == 1.0
    empty = g.normalize_result({})
    assert empty["is_it"] is False and empty["category"] is None


def test_prompt_truncation_and_hashing():
    long_text = "x" * 5000
    item = g.make_item("1", long_text)
    assert len(item.text) == g.MAX_INPUT_CHARS
    assert item.hash == g.input_hash(item.text)
    assert "ref=1" in g.build_prompt([item])
