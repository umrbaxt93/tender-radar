"""Classification pipeline: rules first, cache second, model last."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from radar.classify import gemini as g
from radar.classify.budget import BudgetExceeded, CostLedger, load_pricing
from radar.classify.rules import build_text, classify_text
from radar.config import Settings
from radar.models import AiCache, Classification, LotItem, Procedure

log = logging.getLogger(__name__)


@dataclass
class ClassifyReport:
    considered: int = 0
    by_rule: int = 0
    rule_non_it: int = 0
    from_cache: int = 0
    deduplicated: int = 0
    by_model: int = 0
    batches: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model_name: str | None = None
    stopped_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"classify: considered={self.considered} rule={self.by_rule} "
                f"(non-IT {self.rule_non_it}) cache={self.from_cache} "
                f"deduplicated={self.deduplicated} model={self.by_model} "
                f"batches={self.batches} tokens={self.input_tokens}/{self.output_tokens} "
                f"cost=${self.cost_usd:.6f} model_name={self.model_name} "
                f"stopped={self.stopped_reason}")


def _store(session: Session, procedure_id: int, values: dict) -> None:
    stmt = pg_insert(Classification).values(procedure_id=procedure_id, **values)
    stmt = stmt.on_conflict_do_update(index_elements=[Classification.procedure_id],
                                      set_={k: stmt.excluded[k] for k in values})
    session.execute(stmt)


# The confidence the rules layer stores when it abstains (see rules.py): the row is
# written is_it=false, but nothing was actually decided about it.
UNSURE_CONFIDENCE = Decimal("0.50")


def _pending(session: Session, limit: int | None, refresh: bool,
             unsure_only: bool = False) -> list[tuple[int, str]]:
    stmt = select(Procedure.id, Procedure.title)
    if unsure_only:
        # The only rows where the model adds information. Re-sending lots the rules
        # already decided spends money to relearn what is known.
        stmt = stmt.join(Classification, Classification.procedure_id == Procedure.id).where(
            Classification.method == "rule",
            Classification.confidence == UNSURE_CONFIDENCE,
        )
    elif not refresh:
        stmt = stmt.where(~select(Classification.procedure_id)
                          .where(Classification.procedure_id == Procedure.id).exists())
    stmt = stmt.order_by(Procedure.id)
    if limit:
        stmt = stmt.limit(limit)
    return list(session.execute(stmt).all())


# A long classification run meets transient model errors -- 503 "high demand", 429, 500.
# Ending the whole run on the first one wastes every batch still queued behind it.
MAX_BATCH_ATTEMPTS = 4
BACKOFF_BASE_S = 5.0
MAX_CONSECUTIVE_FAILURES = 5
_TRANSIENT_MARKERS = ("503", "429", "500", "unavailable", "resource_exhausted",
                      "deadline", "timeout", "overloaded", "internal")
_sleep = time.sleep


def _is_transient(exc: Exception) -> bool:
    blob = f"{type(exc).__name__} {exc}".lower()
    return any(m in blob for m in _TRANSIENT_MARKERS)


# PostgreSQL refuses a statement with more than 65535 bind parameters, and one IN clause
# spends one per id. A full-corpus run passes far more than that.
_ID_CHUNK = 10_000


def _item_names(session: Session, procedure_ids: list[int]) -> dict[int, list[str]]:
    names: dict[int, list[str]] = {pid: [] for pid in procedure_ids}
    for start in range(0, len(procedure_ids), _ID_CHUNK):
        rows = session.execute(
            select(LotItem.procedure_id, LotItem.raw_name)
            .where(LotItem.procedure_id.in_(procedure_ids[start:start + _ID_CHUNK]))
        ).all()
        for pid, name in rows:
            names[pid].append(name)
    return names


def run_classification(session: Session, settings: Settings, *, use_ai: bool = True,
                       limit: int | None = None, mock: bool = False, refresh: bool = False,
                       unsure_only: bool = False,
                       batch_size: int = g.DEFAULT_BATCH_SIZE,
                       model: g.Model | None = None) -> ClassifyReport:
    report = ClassifyReport()
    pending = _pending(session, limit, refresh, unsure_only)
    report.considered = len(pending)
    if not pending:
        report.stopped_reason = "nothing_to_do"
        return report

    names = _item_names(session, [pid for pid, _ in pending])
    unsure: list[tuple[int, g.BatchItem]] = []

    for pid, title in pending:
        text = build_text(title, names.get(pid, []))
        rule = classify_text(text)
        if rule.decided:
            _store(session, pid, {
                "is_it": rule.likely_it == "yes",
                "category": rule.category if rule.likely_it == "yes" else None,
                "subcategory": None, "brand": rule.brand, "model_hint": None,
                "is_subscription": rule.is_subscription,
                "term_months": rule.term_months, "method": "rule", "model_name": None,
                "confidence": 0.9, "input_hash": g.input_hash(g.truncate(text)),
                "created_at": datetime.now(UTC),
            })
            report.by_rule += 1
            report.rule_non_it += int(rule.likely_it == "no")
        else:
            unsure.append((pid, g.make_item(str(pid), text)))
    session.commit()

    if not unsure:
        report.stopped_reason = "rules_settled_everything"
        return report
    if not use_ai:
        report.stopped_reason = f"rules_only:{len(unsure)}_unclassified"
        return report

    # Cache lookup before any call.
    remaining: list[tuple[int, g.BatchItem]] = []
    for pid, item in unsure:
        cached = session.get(AiCache, item.hash)
        if cached:
            _store(session, pid, _values_from(cached.response_json, cached.model_name, item.hash))
            report.from_cache += 1
        else:
            remaining.append((pid, item))
    session.commit()

    if not remaining:
        report.stopped_reason = "served_from_cache"
        return report

    # Identical lot text is common (the same licence bought by many customers). Send one
    # representative per hash and fan the answer back out: fewer tokens for the same result.
    by_hash: dict[str, list[tuple[int, g.BatchItem]]] = {}
    for pid, item in remaining:
        by_hash.setdefault(item.hash, []).append((pid, item))
    unique = [entries[0] for entries in by_hash.values()]
    report.deduplicated = len(remaining) - len(unique)

    if model is None:
        if mock:
            model = g.MockModel()
        else:
            if not settings.gemini_api_key:
                report.stopped_reason = "no_gemini_api_key"
                log.warning("GEMINI_API_KEY missing; %d lots left unclassified", len(remaining))
                return report
            model = g.GeminiModel(settings.gemini_api_key, settings.gemini_model)
    report.model_name = model.name

    try:
        pricing = load_pricing(model.name)
    except Exception as exc:  # PricingUnavailable
        report.stopped_reason = f"pricing_unavailable: {exc}"
        log.error("%s", exc)
        return report
    ledger = CostLedger(session, settings.classifier_budget_usd, pricing)

    consecutive_failures = 0
    for start in range(0, len(unique), batch_size):
        chunk = unique[start:start + batch_size]
        items = [item for _, item in chunk]
        prompt = g.build_prompt(items)
        est_in, est_out = g.estimate_tokens(prompt, len(items))
        try:
            row = ledger.reserve(prompt, est_in, est_out)
        except BudgetExceeded as exc:
            report.stopped_reason = f"budget_exceeded: {exc}"
            log.warning("stopping classification: %s", exc)
            break
        response = None
        for attempt in range(1, MAX_BATCH_ATTEMPTS + 1):
            try:
                response = model.generate(prompt, len(items))
                break
            except Exception as exc:
                ledger.fail(row)
                if not _is_transient(exc) or attempt == MAX_BATCH_ATTEMPTS:
                    report.errors.append(f"batch at {start}: {type(exc).__name__}: {exc}")
                    log.error("model call failed: %s", exc)
                    break
                wait = BACKOFF_BASE_S * (2 ** (attempt - 1))
                log.warning("model call failed (%s), retrying in %.0fs (attempt %d/%d)",
                            type(exc).__name__, wait, attempt, MAX_BATCH_ATTEMPTS)
                _sleep(wait)
                try:
                    row = ledger.reserve(prompt, est_in, est_out)
                except BudgetExceeded as exc:
                    report.stopped_reason = f"budget_exceeded: {exc}"
                    break

        if response is None:
            if report.stopped_reason:
                break
            # One dead batch out of thousands must not end the run. A systemic fault --
            # a rejected key, a withdrawn model -- fails every batch, so consecutive
            # failures are what stops it.
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                report.stopped_reason = (
                    f"{consecutive_failures} consecutive batch failures; stopping")
                log.error("%s", report.stopped_reason)
                break
            continue
        consecutive_failures = 0
        by_ref = {str(r.get("ref")): r for r in response.results}
        missing = 0
        for _pid, item in chunk:
            raw = by_ref.get(item.ref)
            if raw is None:
                missing += 1
                continue
            values = g.normalize_result(raw)
            session.merge(AiCache(input_hash=item.hash, response_json=values,
                                  model_name=model.name))
            for twin_pid, _ in by_hash[item.hash]:
                _store(session, twin_pid, _values_from(values, model.name, item.hash))
                report.by_model += 1
        if missing:
            report.errors.append(f"batch at {start}: {missing} lots missing from the answer")
        actual = ledger.settle(row, response.input_tokens, response.output_tokens)
        report.batches += 1
        report.input_tokens += response.input_tokens
        report.output_tokens += response.output_tokens
        report.cost_usd += float(actual)
        session.commit()

    report.stopped_reason = report.stopped_reason or "completed"
    return report


def _values_from(values: dict, model_name: str, hash_: str) -> dict:
    return {
        "is_it": values["is_it"], "category": values["category"],
        "subcategory": values["subcategory"], "brand": values["brand"],
        "model_hint": values["model_hint"], "is_subscription": values["is_subscription"],
        "term_months": values["term_months"], "method": "ai", "model_name": model_name,
        "confidence": values["confidence"], "input_hash": hash_,
        "created_at": datetime.now(UTC),
    }
