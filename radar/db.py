"""Engine and session helpers. One engine per process, single worker."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from radar.config import load_settings

_engine: Engine | None = None


def normalize_url(url: str) -> str:
    """Force the psycopg 3 driver so that plain postgresql:// URLs work."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def get_engine(url: str | None = None) -> Engine:
    global _engine
    if url is not None:
        return create_engine(normalize_url(url), pool_pre_ping=True, future=True)
    if _engine is None:
        _engine = create_engine(
            normalize_url(load_settings().require_database()), pool_pre_ping=True, future=True
        )
    return _engine


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    factory = sessionmaker(bind=engine or get_engine(), expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
