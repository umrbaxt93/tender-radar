"""Keyword and regex pre-filter over title + lot item names.

The rules layer exists to keep AI spend low: anything it can decide is never sent to
Gemini. Its verdict is one of:

  no      - a non-IT keyword matched and no IT keyword did. Stored as method='rule',
            is_it=false. Never reaches the AI.
  yes     - IT keywords matched with a single dominant category. Stored as
            method='rule' with that category.
  unsure  - ambiguous or no match. Only these rows are eligible for AI classification.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

KEYWORDS_PATH = Path(__file__).with_name("keywords.yaml")

CATEGORIES = (
    "Server", "Storage", "Network", "Firewall", "Antivirus/EDR", "DLP", "SIEM/SOC",
    "Cybersecurity-Other", "Microsoft", "Google Workspace", "Collaboration",
    "Software Licenses", "Cloud", "Computer/Notebook", "Printer/MFP", "UPS", "CCTV",
    "Data Center", "IT Services", "Software Development", "Telecom", "Other IT",
)

# Categories whose keywords are generic enough that a single hit is not proof of a
# specific category; a more specific hit elsewhere wins.
_WEAK_CATEGORIES = {"Software Licenses", "Other IT", "IT Services"}


@dataclass
class RuleResult:
    likely_it: str  # 'yes' | 'no' | 'unsure'
    category: str | None = None
    brand: str | None = None
    is_subscription: bool = False
    term_months: int | None = None
    matched: list[str] = field(default_factory=list)
    not_it_matched: list[str] = field(default_factory=list)

    @property
    def decided(self) -> bool:
        return self.likely_it in ("yes", "no")


def normalize(text: str) -> str:
    """Lowercase, strip accents that vary between sources, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = text.replace("ʻ", "'").replace("‘", "'").replace("’", "'").replace("`", "'")
    text = text.replace("ё", "е")
    return " ".join(text.split())


def _compile(entry: str) -> re.Pattern[str]:
    if entry.startswith("re:"):
        return re.compile(entry[3:], re.IGNORECASE)
    return re.compile(re.escape(normalize(entry)), re.IGNORECASE)


@lru_cache(maxsize=1)
def load_keywords(path: Path = KEYWORDS_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    compiled: dict[str, Any] = {
        "categories": {name: [_compile(e) for e in entries]
                       for name, entries in raw["categories"].items()},
        "not_it": [_compile(e) for e in raw["not_it"]],
        "subscription": [_compile(e) for e in raw["subscription"]],
        "term_patterns": [re.compile(p[3:], re.IGNORECASE) for p in raw["term_patterns"]],
        "brands": {brand: [_compile(e) for e in aliases]
                   for brand, aliases in raw["brands"].items()},
    }
    unknown = set(compiled["categories"]) - set(CATEGORIES)
    if unknown:
        raise ValueError(f"keywords.yaml has unknown categories: {sorted(unknown)}")
    return compiled


def build_text(title: str, item_names: list[str] | None = None) -> str:
    parts = [title or ""]
    parts.extend(item_names or [])
    return normalize(" \n ".join(p for p in parts if p))


def detect_term_months(text: str, keywords: dict[str, Any] | None = None) -> int | None:
    """Return a plausible subscription term in months, or None."""
    keywords = keywords or load_keywords()
    best: int | None = None
    for pattern in keywords["term_patterns"]:
        for match in pattern.finditer(text):
            value = int(match.group(1))
            months = value if "oy" in match.group(0) or "month" in match.group(0) \
                or "ой" in match.group(0) or "месяц" in match.group(0) else value * 12
            if 1 <= months <= 120 and (best is None or months > best):
                best = months
    return best


def detect_brand(text: str, keywords: dict[str, Any] | None = None) -> str | None:
    keywords = keywords or load_keywords()
    for brand, patterns in keywords["brands"].items():
        if any(p.search(text) for p in patterns):
            return brand
    return None


def classify_text(text: str, keywords: dict[str, Any] | None = None) -> RuleResult:
    keywords = keywords or load_keywords()
    hits: dict[str, list[str]] = {}
    for category, patterns in keywords["categories"].items():
        found = [m.group(0) for p in patterns if (m := p.search(text))]
        if found:
            hits[category] = found
    not_it = [m.group(0) for p in keywords["not_it"] if (m := p.search(text))]

    subscription = any(p.search(text) for p in keywords["subscription"])
    term = detect_term_months(text, keywords)
    brand = detect_brand(text, keywords)
    matched = sorted({h for found in hits.values() for h in found})

    if not hits:
        verdict = "no" if not_it else "unsure"
        return RuleResult(verdict, None, None, False, None, matched, not_it)

    strong = {c: h for c, h in hits.items() if c not in _WEAK_CATEGORIES}
    ranked = strong or hits
    # Most specific category wins: more distinct matches first, then the strong set.
    category = max(ranked, key=lambda c: (len(set(ranked[c])), c not in _WEAK_CATEGORIES))

    if not_it and not strong:
        # Generic IT wording inside an obviously non-IT purchase: let the AI decide.
        return RuleResult("unsure", category, brand, subscription, term, matched, not_it)
    if not_it and strong:
        # Mixed signals with a specific IT match: keep it, but do not claim certainty.
        return RuleResult("unsure", category, brand, subscription, term, matched, not_it)
    if strong:
        return RuleResult("yes", category, brand, subscription, term, matched, not_it)
    return RuleResult("unsure", category, brand, subscription, term, matched, not_it)


def classify_procedure(title: str, item_names: list[str] | None = None) -> RuleResult:
    return classify_text(build_text(title, item_names))
