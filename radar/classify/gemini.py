"""Gemini classification with JSON schema, batching and a deterministic offline mock.

Cost controls, in order: the rules layer decides most rows for free, the ai_cache skips
anything already answered, batches carry ~20 lots per call, each input is truncated, and the
CostLedger reserves the estimated price before the call. The mock model exercises all of
that offline so the $10 stop is proven before any paid batch.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from radar.classify.rules import CATEGORIES, RuleResult, classify_text

log = logging.getLogger(__name__)

MAX_INPUT_CHARS = 2500
DEFAULT_BATCH_SIZE = 20
# Preference order when GEMINI_MODEL is unset: cheapest tier first (docs/SPEC.md).
MODEL_PREFERENCE = ("flash-lite", "flash")

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string"},
                    "is_it": {"type": "boolean"},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "subcategory": {"type": "string"},
                    "brand": {"type": "string"},
                    "model_hint": {"type": "string"},
                    "is_subscription": {"type": "boolean"},
                    "term_months": {"type": "integer"},
                    "confidence": {"type": "number"},
                    "summary": {"type": "string"},
                },
                "required": ["ref", "is_it", "category", "is_subscription", "confidence"],
            },
        }
    },
    "required": ["results"],
}

PROMPT_HEADER = (
    "You classify Uzbek public procurement lots for an IT sales team. Input lots are in "
    "Uzbek-Latin, Uzbek-Cyrillic or Russian. For each lot decide whether it is an IT "
    "purchase and fill the schema. Use only these categories: "
    + ", ".join(CATEGORIES) + ". "
    "is_subscription means a licence, subscription, support or hosting term that will need "
    "renewing. term_months is the stated term in months, omitted when not stated. "
    "confidence is 0..1. Answer for every ref, in the same order. Return JSON only.\n\n"
)


def input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def truncate(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit]


@dataclass(frozen=True)
class BatchItem:
    ref: str            # stable reference inside the batch (the procedure id as a string)
    text: str           # normalized title + item names
    hash: str           # sha256 of the truncated text, the ai_cache key


def make_item(ref: str, text: str) -> BatchItem:
    body = truncate(text)
    return BatchItem(ref=ref, text=body, hash=input_hash(body))


def build_prompt(items: list[BatchItem]) -> str:
    lines = [PROMPT_HEADER]
    for item in items:
        lines.append(f"### ref={item.ref}\n{item.text}\n")
    return "\n".join(lines)


def estimate_tokens(prompt: str, item_count: int) -> tuple[int, int]:
    """Rough pre-call estimate: ~4 chars per token in, ~60 tokens of JSON per lot out."""
    return max(1, len(prompt) // 4), max(1, item_count * 60)


@dataclass
class ModelResponse:
    results: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int


class Model(Protocol):
    name: str

    def generate(self, prompt: str, item_count: int) -> ModelResponse: ...


def normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Clamp a model answer into the shape the database accepts."""
    category = raw.get("category")
    if category not in CATEGORIES:
        category = "Other IT" if raw.get("is_it") else None
    term = raw.get("term_months")
    if not isinstance(term, int) or not 1 <= term <= 120:
        term = None
    try:
        confidence = float(raw.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "is_it": bool(raw.get("is_it")),
        "category": category,
        "subcategory": (raw.get("subcategory") or None),
        "brand": (raw.get("brand") or None),
        "model_hint": (raw.get("model_hint") or None),
        "is_subscription": bool(raw.get("is_subscription")),
        "term_months": term,
        "confidence": min(max(confidence, 0.0), 1.0),
        "summary": (raw.get("summary") or None),
    }


class MockModel:
    """Deterministic offline model. Never contacts a network; mirrors the rules layer.

    Results from this model are always stored with model_name='mock' so no report can
    present them as real Gemini output.
    """

    name = "mock"

    def generate(self, prompt: str, item_count: int) -> ModelResponse:
        results = []
        for block in prompt.split("### ref=")[1:]:
            ref, _, text = block.partition("\n")
            rule: RuleResult = classify_text(text.strip())
            is_it = rule.likely_it != "no" and rule.category is not None
            results.append({
                "ref": ref.strip(),
                "is_it": is_it,
                "category": rule.category if is_it else "Other IT",
                "subcategory": "",
                "brand": rule.brand or "",
                "model_hint": "",
                "is_subscription": rule.is_subscription,
                "term_months": rule.term_months or 0,
                "confidence": 0.6 if is_it else 0.55,
                "summary": "offline mock classification",
            })
        prompt_tokens, output_tokens = estimate_tokens(prompt, item_count)
        return ModelResponse(results, prompt_tokens, output_tokens)


class GeminiModel:
    """Thin google-genai wrapper. Constructed only when a paid run is explicitly requested."""

    def __init__(self, api_key: str, model_name: str, client: Any | None = None) -> None:
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self.name = model_name
        self._client = client
        self._api_key = api_key

    @property
    def client(self) -> Any:
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def generate(self, prompt: str, item_count: int) -> ModelResponse:
        from google.genai import types

        response = self.client.models.generate_content(
            model=self.name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                temperature=0.0,
            ),
        )
        payload = json.loads(response.text)
        usage = getattr(response, "usage_metadata", None)
        return ModelResponse(
            results=payload.get("results", []),
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
        )


def choose_model_name(client: Any, configured: str = "") -> str:
    """Use GEMINI_MODEL when set; otherwise list models and pick the cheapest tier.

    The chosen name is logged. Listing does not return prices, so the caller still has to
    have a reviewed price for whatever comes back (radar/classify/pricing.yaml).
    """
    if configured:
        log.info("using configured Gemini model %s", configured)
        return configured
    names = [m.name.split("/")[-1] for m in client.models.list()]
    for tier in MODEL_PREFERENCE:
        for name in sorted(names):
            if tier in name:
                log.info("selected Gemini model %s from tier %s", name, tier)
                return name
    raise RuntimeError(f"no flash-lite or flash model available; saw {names[:10]}")
