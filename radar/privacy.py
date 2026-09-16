"""Privacy protection, PII masking, and AI input sanitization.

In compliance with Law of the Republic of Uzbekistan No. ZRU-547 "On Personal Data":
- 9-digit identifiers are Legal Entity STIR (inn) -> Public data, displayed in full.
- 14-digit identifiers are Physical Person / Individual Entrepreneur JSHSHIR (PINFL)
  -> Masked as '*********12345' (first 9 digits masked, last 5 visible).
  -> Only accessible by users with 'admin' role, with all accesses recorded in audit_log.
- AI sanitization strips STIR, JSHSHIR, phone numbers, and emails before sending to LLMs.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from radar.models import AuditLog

log = logging.getLogger(__name__)

# Regex patterns for sanitization
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_RE_JSHSHIR = re.compile(r"(?<!\d)\d{14}(?!\d)")
_RE_PHONE_UZ = re.compile(
    r"(?<!\d)(?:\+?998[-.\s]?(?:\(?\d{2}\)?[-.\s]?)?\d{3}[-.\s]?\d{2}[-.\s]?\d{2}|\(?\d{2}\)?[-.\s]\d{3}[-.\s]?\d{2}[-.\s]?\d{2})(?!\d)"
)
_RE_STIR = re.compile(r"(?<!\d)\d{9}(?!\d)")


def is_jshshir(identifier: str | None) -> bool:
    """Return True if the identifier is a 14-digit physical person PINFL / JSHSHIR."""
    if not identifier:
        return False
    clean = re.sub(r"\D", "", str(identifier).strip())
    return len(clean) == 14


def is_stir(identifier: str | None) -> bool:
    """Return True if the identifier is a 9-digit legal entity STIR / INN."""
    if not identifier:
        return False
    clean = re.sub(r"\D", "", str(identifier).strip())
    return len(clean) == 9


def mask_identifier(identifier: str | None, is_admin: bool = False) -> str:
    """Format and mask identifier according to role and entity type.

    If 14 digits (JSHSHIR):
      - If is_admin is True: returns original full identifier.
      - Else: returns '*********12345' (first 9 masked with *, last 5 digits visible).
    If 9 digits (STIR) or other: returns original identifier.
    """
    if not identifier:
        return ""
    clean = str(identifier).strip()
    digits = re.sub(r"\D", "", clean)

    if len(digits) == 14:
        if is_admin:
            return clean
        # Mask first 9 digits, keep last 5
        return f"{'*' * 9}{digits[-5:]}"

    return clean


def sanitize_for_ai(text: str | None) -> str:
    """Strip personal identifiers, phone numbers, and emails from text before sending to LLMs."""
    if not text:
        return ""

    sanitized = str(text)
    # 1. Emails
    sanitized = _RE_EMAIL.sub("[EMAIL]", sanitized)
    # 2. 14-digit JSHSHIR / PINFL
    sanitized = _RE_JSHSHIR.sub("[PINFL]", sanitized)
    # 3. Phone numbers
    sanitized = _RE_PHONE_UZ.sub("[PHONE]", sanitized)
    # 4. 9-digit STIR
    sanitized = _RE_STIR.sub("[STIR]", sanitized)

    return sanitized


def record_audit_event(
    session: Session,
    user_id: int,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Record an entry in the audit_log table."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip_address,
    )
    session.add(entry)
    log.info(
        "AUDIT: User %d performed '%s' on %s:%s from IP %s",
        user_id,
        action,
        target_type or "-",
        target_id or "-",
        ip_address or "-",
    )
    return entry
