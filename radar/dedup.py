"""Deduplication and cross-source record merging for procedures and renewals."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from radar.models import Procedure, RenewalOpportunity

log = logging.getLogger(__name__)


def find_and_merge_duplicates(session: Session) -> dict[str, Any]:
    """Identify and merge duplicate procedures across or within platforms.

    Criteria:
      Same customer STIR + same supplier STIR + identical award amount +
      completion date within +/- 3 days (259,200 seconds).

    The newer / secondary procedure (higher id) is linked to the primary (lower id)
    via `merged_from_id = p1.id` and removed from `renewal_opportunity`.
    """
    query = text("""
        SELECT
            p1.id AS primary_id,
            p1.source AS primary_source,
            p1.source_id AS primary_source_id,
            p2.id AS duplicate_id,
            p2.source AS duplicate_source,
            p2.source_id AS duplicate_source_id,
            c1.stir AS customer_stir,
            s1.stir AS supplier_stir,
            a1.amount AS amount,
            p1.completed_at AS primary_date,
            p2.completed_at AS duplicate_date
        FROM procedure p1
        JOIN procedure p2 ON p1.id < p2.id AND p2.merged_from_id IS NULL
        JOIN organization c1 ON p1.customer_org_id = c1.id
        JOIN organization c2 ON p2.customer_org_id = c2.id
             AND c1.stir = c2.stir AND c1.stir IS NOT NULL
        JOIN award a1 ON a1.procedure_id = p1.id
        JOIN award a2 ON a2.procedure_id = p2.id AND a1.amount = a2.amount
        JOIN organization s1 ON a1.supplier_org_id = s1.id
        JOIN organization s2 ON a2.supplier_org_id = s2.id
             AND s1.stir = s2.stir AND s1.stir IS NOT NULL
        WHERE p1.completed_at IS NOT NULL AND p2.completed_at IS NOT NULL
          AND ABS(EXTRACT(EPOCH FROM (p1.completed_at - p2.completed_at))) <= 3 * 86400
        ORDER BY p1.id ASC, p2.id ASC;
    """)

    rows = session.execute(query).fetchall()
    merged_count = 0
    details = []

    for r in rows:
        prim_id = r.primary_id
        dup_id = r.duplicate_id

        dup_proc = session.get(Procedure, dup_id)
        if not dup_proc or dup_proc.merged_from_id is not None:
            continue

        dup_proc.merged_from_id = prim_id

        # Clean up any renewal opportunities attached to the duplicate
        session.execute(
            delete(RenewalOpportunity).where(RenewalOpportunity.procedure_id == dup_id)
        )

        merged_count += 1
        details.append({
            "primary_id": prim_id,
            "primary_source": r.primary_source,
            "primary_source_id": r.primary_source_id,
            "duplicate_id": dup_id,
            "duplicate_source": r.duplicate_source,
            "duplicate_source_id": r.duplicate_source_id,
            "customer_stir": r.customer_stir,
            "supplier_stir": r.supplier_stir,
            "amount": float(r.amount) if r.amount is not None else 0.0,
        })
        log.info(
            "Merged duplicate procedure %d (%s:%s) into primary %d (%s:%s)",
            dup_id, r.duplicate_source, r.duplicate_source_id,
            prim_id, r.primary_source, r.primary_source_id,
        )

    session.commit()
    return {
        "found": len(rows),
        "merged": merged_count,
        "details": details,
    }
