"""Authentication, password hashing, session management and RBAC."""

from __future__ import annotations

import hmac
import logging
import os
import secrets
from datetime import UTC, datetime
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from slowapi import Limiter
from slowapi.util import get_remote_address

from radar.db import session_scope
from radar.models import User

log = logging.getLogger("radar.auth")

# Password hasher using Argon2id
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

# Session serializer secret key
SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "radar-insecure-secret-change-in-production")
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="radar-session-salt")

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)

SESSION_COOKIE_NAME = "radar_session"
SESSION_MAX_AGE_SECONDS = 8 * 3600  # 8 hours


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _ph.hash(password)


def verify_password(hash_str: str, password: str) -> bool:
    """Verify password against Argon2id hash. Returns True if valid."""
    try:
        return _ph.verify(hash_str, password)
    except VerifyMismatchError:
        return False
    except Exception as exc:
        log.warning("Password verification error: %s", exc)
        return False


def create_session_token(user_id: int, username: str, role: str) -> str:
    """Create a signed session token containing user identity and nonce."""
    payload = {
        "sub": user_id,
        "name": username,
        "role": role,
        "csrf": secrets.token_hex(16),
        "iat": datetime.now(UTC).timestamp(),
    }
    return _serializer.dumps(payload)


def verify_session_token(token: str) -> dict | None:
    """Verify and decode signed session token within max age."""
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return data
    except (BadSignature, SignatureExpired):
        return None


def get_current_user_optional(
    radar_session: Annotated[str | None, Cookie()] = None,
) -> User | None:
    """Extract authenticated user if session cookie is present and valid."""
    if not radar_session:
        return None
    data = verify_session_token(radar_session)
    if not data or "sub" not in data:
        return None

    with session_scope() as session:
        user = session.get(User, data["sub"])
        if user and user.is_active:
            return user
    return None


def get_current_user(
    current_user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    """Enforce authentication. Returns active User or raises HTTP 401."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentifikatsiyadan o'tilmagan. Iltimos, tizimga kiring.",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return current_user


def require_role(*allowed_roles: str):
    """Dependency factory ensuring current user has one of allowed roles."""

    def role_checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Ushbu amal uchun ruxsat yo'q. Talab qilinadi: {', '.join(allowed_roles)}",
            )
        return user

    return role_checker


def verify_csrf_token(request: Request, csrf_token: str | None = None) -> bool:
    """Verify CSRF token against session token payload."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return False
    data = verify_session_token(cookie)
    if not data or "csrf" not in data:
        return False
    expected = data["csrf"]
    actual = csrf_token or request.headers.get("X-CSRF-Token")
    if not actual:
        return False
    return hmac.compare_digest(expected, actual)
