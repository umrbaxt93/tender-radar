"""Comprehensive security and authentication test suite for Phase 0 AppSec hardening."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from radar.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    hash_password,
)
from radar.db import session_scope
from radar.models import Classification, ExportLog, Organization, Procedure, User
from radar.security import sanitize_for_spreadsheet
from radar.web import app

client = TestClient(app)


@pytest.fixture
def auth_user():
    """Create a verified test user with known credentials."""
    username = f"test_user_{os.urandom(4).hex()}"
    pwd = "TestSecurePassword123!"
    with session_scope() as session:
        user = User(
            username=username,
            password_hash=hash_password(pwd),
            role="sales",
            is_active=True,
        )
        session.add(user)
        session.commit()
        user_id = user.id

    yield {"id": user_id, "username": username, "password": pwd}

    with session_scope() as session:
        u = session.get(User, user_id)
        if u:
            session.delete(u)
            session.commit()


@pytest.fixture
def auth_cookie(auth_user):
    """Generate a valid signed session cookie."""
    token = create_session_token(auth_user["id"], auth_user["username"], "sales")
    return {SESSION_COOKIE_NAME: token}


def test_anonymous_requests_rejected():
    """Verify that unauthenticated access to protected endpoints is rejected."""
    # 1. Dashboard redirects anonymous users to /login
    resp = client.get("/radar", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")

    # 2. JSON APIs return 401 Unauthorized
    resp_api = client.get("/api/search")
    assert resp_api.status_code == 401
    assert "Autentifikatsiyadan o'tilmagan" in resp_api.json()["detail"]

    # 3. Export API returns 401
    resp_export = client.get("/api/export/xlsx")
    assert resp_export.status_code == 401


def test_login_success_and_cookie_flags(auth_user):
    """Verify valid login sets secure, HttpOnly session cookie."""
    resp = client.post(
        "/login",
        data={
            "username": auth_user["username"],
            "password": auth_user["password"],
            "next": "/radar",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers.get("location") == "/radar"

    # Verify cookie attributes
    cookie_header = resp.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in cookie_header
    assert "HttpOnly" in cookie_header or "httponly" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()


def test_login_rate_limiting():
    """Verify that excessive failed login attempts trigger HTTP 429 rate limit."""
    # Make 5 failed attempts (allowed under 5/minute limit)
    for _ in range(5):
        client.post(
            "/login",
            data={"username": "non_existent", "password": "wrong_password"},
        )

    # 6th attempt should trigger 429 Too Many Requests
    resp = client.post(
        "/login",
        data={"username": "non_existent", "password": "wrong_password"},
    )
    assert resp.status_code == 429


def test_export_xlsx_audit_logging(auth_user, auth_cookie):
    """Verify XLSX export downloads properly and writes an audit record in export_log."""
    # Seed a minimal procedure with IT classification so export is non-empty
    with session_scope() as session:
        org = Organization(stir=f"999{os.urandom(3).hex()}", name_canonical="Test Customer")
        session.add(org)
        session.flush()

        proc = Procedure(
            source="uzex",
            source_id=f"test_proc_{os.urandom(4).hex()}",
            customer_org_id=org.id,
            title="Lenovo Server Upgrade",
            start_price=10000000.0,
            completed_at=datetime.now(UTC),
        )
        session.add(proc)
        session.flush()

        cls = Classification(
            procedure_id=proc.id,
            is_it=True,
            category="Server",
            method="rule",
            confidence=1.0,
        )
        session.add(cls)
        session.commit()
        proc_id = proc.id

    try:
        # Request export as authenticated user
        client.cookies.set(SESSION_COOKIE_NAME, auth_cookie[SESSION_COOKIE_NAME])
        resp = client.get("/api/export/xlsx?limit=10")
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in content_type

        # Verify audit log entry
        with session_scope() as session:
            log_entry = session.scalar(
                select(ExportLog).where(ExportLog.user_id == auth_user["id"])
            )
            assert log_entry is not None
            assert log_entry.export_type == "xlsx"
    finally:
        client.cookies.clear()
        with session_scope() as session:
            c = session.get(Classification, proc_id)
            if c:
                session.delete(c)
            p = session.get(Procedure, proc_id)
            if p:
                session.delete(p)
            session.commit()


def test_formula_injection_sanitized():
    """Verify spreadsheet formula injection characters are prepended with single quote."""
    assert sanitize_for_spreadsheet("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert sanitize_for_spreadsheet("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_for_spreadsheet("-2+3*[1]!$A$1") == "'-2+3*[1]!$A$1"
    assert sanitize_for_spreadsheet("@IMPORT_DATA") == "'@IMPORT_DATA"
    assert sanitize_for_spreadsheet("Normal Product Name") == "Normal Product Name"
    assert sanitize_for_spreadsheet("") == ""
    assert sanitize_for_spreadsheet(None) == ""


def test_xss_escaping_in_radar_template():
    """Verify dangerous HTML in lot titles is escaped by Jinja2 autoescape."""
    from radar.web import TEMPLATES

    xss_payload = '<script>alert("XSS")</script>'
    template = TEMPLATES.get_template("radar.html")
    # Render with a mock row having an XSS payload in title
    rendered = template.render({
        "rows": [
            type("MockRow", (), {
                "customer": "Test Customer",
                "stir": "123456789",
                "region": "Tashkent",
                "category": "Server",
                "brand": "Lenovo",
                "last_purchase_at": datetime.now(UTC),
                "amount": 1000000.0,
                "expected_renewal_at": datetime.now(UTC),
                "contact_by_at": datetime.now(UTC),
                "score": 85,
                "source_url": "https://xarid.uzex.uz",
                "title": xss_payload,
            })()
        ],
        "stats": {"classified_it": 1, "organizations": 1, "ai_spent_usd": 0.0},
        "current_user": type("MockUser", (), {"username": "admin", "role": "admin"})(),
        "generated_at": "2026-09-15 12:00 UTC",
        "synthetic_sources": [],
        "due_now": 0,
        "max_score": 100,
        "window_days": 60,
    })

    # Ensure unescaped raw payload does NOT appear in HTML
    assert '<script>alert("XSS")</script>' not in rendered
    # Ensure escaped version appears
    escaped_xss = "&lt;script&gt;alert(&#34;XSS&#34;)&lt;/script&gt;"
    assert escaped_xss in rendered or "&lt;script&gt;" in rendered

