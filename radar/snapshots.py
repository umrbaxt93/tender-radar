"""raw_snapshot storage: zstd-compressed bodies keyed by sha256, re-parseable later."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import zstandard
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.models import RawSnapshot

_cctx = zstandard.ZstdCompressor(level=6)
_dctx = zstandard.ZstdDecompressor()


def sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def compress(body: bytes) -> bytes:
    return _cctx.compress(body)


def decompress(blob: bytes) -> bytes:
    return _dctx.decompress(blob)


def store_snapshot(session: Session, url: str, body: bytes,
                   fetched_at: datetime | None = None) -> RawSnapshot:
    """Insert a snapshot; reuse an identical (url, sha256) row to stay idempotent."""
    digest = sha256_hex(body)
    existing = session.scalar(
        select(RawSnapshot).where(RawSnapshot.sha256 == digest, RawSnapshot.url == url)
    )
    if existing:
        return existing
    snap = RawSnapshot(url=url, fetched_at=fetched_at or datetime.now(UTC),
                       sha256=digest, body=compress(body))
    session.add(snap)
    session.flush()
    return snap


def snapshot_body(snap: RawSnapshot) -> bytes:
    body = decompress(snap.body)
    if sha256_hex(body) != snap.sha256:
        raise ValueError(f"snapshot {snap.id} checksum mismatch")
    return body
