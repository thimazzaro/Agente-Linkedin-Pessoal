"""
Security utilities: rate limiting, security headers middleware,
startup validation, and input sanitization.
"""
import os
import re
import time
import logging
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger("linkedin_agent.security")

# Review tokens expire after this many hours
TOKEN_EXPIRY_HOURS = 72

# ── Required env vars ─────────────────────────────────────────────────────────

REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "TAVILY_API_KEY",
    "LINKEDIN_ACCESS_TOKEN",
    "LINKEDIN_PERSON_URN",
    "RESEND_API_KEY",
    "APP_BASE_URL",
    "TRIGGER_SECRET",
]

INSECURE_DEFAULTS = {
    "TRIGGER_SECRET": "changeme",
}

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_HTML_RE = re.compile(r"<[^>]+>")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ── Startup validation ────────────────────────────────────────────────────────

def validate_startup_secrets() -> None:
    """Log warnings for missing or insecure env vars at startup."""
    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    if missing:
        logger.warning("SECURITY: Missing env vars — %s", ", ".join(missing))

    for key, bad_value in INSECURE_DEFAULTS.items():
        val = os.environ.get(key, "")
        if val and val == bad_value:
            logger.error(
                "SECURITY: %s is set to an insecure default value. "
                "Regenerate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"",
                key,
            )

    # Warn if APP_BASE_URL is localhost (typical misconfiguration in production)
    base_url = os.environ.get("APP_BASE_URL", "")
    if base_url and "localhost" in base_url and os.environ.get("RAILWAY_ENVIRONMENT"):
        logger.warning("SECURITY: APP_BASE_URL points to localhost but RAILWAY_ENVIRONMENT is set.")


# ── Token expiry ──────────────────────────────────────────────────────────────

def is_token_expired(created_at: datetime | None) -> bool:
    """Returns True if the review token has expired (based on created_at + TOKEN_EXPIRY_HOURS)."""
    if created_at is None:
        return False  # legacy posts without created_at — allow
    expiry = created_at + timedelta(hours=TOKEN_EXPIRY_HOURS)
    return datetime.utcnow() > expiry


# ── Input validation ──────────────────────────────────────────────────────────

def is_valid_uuid(value: str) -> bool:
    """Returns True if value is a valid v4 UUID string."""
    return bool(_UUID_RE.match(value))


def sanitize_feedback(text: str, max_length: int = 500) -> str:
    """Strip HTML tags and control characters; cap length."""
    clean = _HTML_RE.sub("", text)
    clean = _CTRL_RE.sub("", clean)
    return clean[:max_length].strip()


# ── Rate limiter ──────────────────────────────────────────────────────────────

class RateLimiter:
    """Simple in-memory token-bucket rate limiter (per string key)."""

    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        bucket = self._requests[key]
        # Evict old entries
        self._requests[key] = [t for t in bucket if t > cutoff]
        if len(self._requests[key]) >= max_requests:
            return False
        self._requests[key].append(now)
        return True

    def cleanup(self, max_age_seconds: int = 3600) -> None:
        cutoff = time.monotonic() - max_age_seconds
        stale = [k for k, ts in self._requests.items() if not ts or max(ts) < cutoff]
        for k in stale:
            del self._requests[k]


rate_limiter = RateLimiter()


# ── Security headers ASGI middleware ──────────────────────────────────────────

class SecurityHeadersMiddleware:
    """Injects HTTP security headers into every response."""

    _HEADERS = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"x-xss-protection", b"1; mode=block"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", b"geolocation=(), camera=(), microphone=()"),
        (b"cache-control", b"no-store"),
    ]

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def patched_send(message):
            if message["type"] == "http.response.start":
                existing = dict(message.get("headers", []))
                for name, value in self._HEADERS:
                    existing.setdefault(name, value)
                message = {**message, "headers": list(existing.items())}
            await send(message)

        await self.app(scope, receive, patched_send)
