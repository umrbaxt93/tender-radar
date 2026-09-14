"""Shared fixtures. Database tests need PostgreSQL 16 reachable via TEST_DATABASE_URL."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from radar.config import ROOT
from radar.db import get_engine
from radar.models import Base

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
SAMPLES = ROOT / "samples" / "synthetic"


@pytest.fixture(autouse=True)
def _isolate_source_env(monkeypatch):
    monkeypatch.delenv("UZEX_LIST_URL", raising=False)
    monkeypatch.delenv("UZEX_DETAIL_URL", raising=False)


def _engine_or_skip():
    if not TEST_DB_URL:
        pytest.skip("TEST_DATABASE_URL not set; database tests skipped")
    engine = get_engine(TEST_DB_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"test database unreachable: {exc}")
    return engine


@pytest.fixture(scope="session")
def engine():
    engine = _engine_or_skip()
    env = {**os.environ, "DATABASE_URL": TEST_DB_URL}
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], cwd=ROOT, env=env,
                   check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env,
                   check=True, capture_output=True)
    return engine


@pytest.fixture
def session(engine) -> Session:
    with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def samples_dir() -> Path:
    return SAMPLES
