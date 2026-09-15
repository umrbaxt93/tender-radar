"""Security headers middleware, formula injection sanitizer, and AppSec hardening."""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


def sanitize_for_spreadsheet(value: str | None) -> str:
    """Neutralize spreadsheet formula injection (CSV/XLSX injection).

    Prepend a single quote (') if the string begins with '=', '+', '-', or '@'.
    """
    if not value:
        return ""
    val_str = str(value)
    if val_str and val_str[0] in ("=", "+", "-", "@"):
        return "'" + val_str
    return val_str


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds essential defense-in-depth HTTP security headers to all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # HSTS (1 year, subdomains)
        if request.url.scheme == "https" or os.environ.get("APP_ENV") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Frame Protection
        response.headers["X-Frame-Options"] = "DENY"

        # MIME Sniffing Protection
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Referrer Policy
        response.headers["Referrer-Policy"] = "no-referrer"

        # Content Security Policy (strict self, cdn tailwind & xlsx allowed)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com "
            "https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response.headers["Content-Security-Policy"] = csp

        return response
