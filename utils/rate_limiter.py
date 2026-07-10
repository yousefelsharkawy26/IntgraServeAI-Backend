# utils/rate_limiter.py
"""
Custom in-memory rate limiter for FastAPI endpoints.

Tracks request counts per (client_ip, identifier) within a sliding time window.
Designed for auth endpoints to prevent brute-force attacks.
"""

import time
import threading
from typing import Optional, Dict, List, Callable
from fastapi import Request, HTTPException, status
from pydantic import BaseModel


class RateLimitExceeded(HTTPException):
    """Raised when a client exceeds the configured rate limit."""
    def __init__(self, detail: str = "Rate limit exceeded. Please try again later."):
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


class RateLimitRule(BaseModel):
    """Configuration for a single rate-limit rule."""
    max_requests: int
    window_seconds: int


class InMemoryRateLimiter:
    """
    Thread-safe in-memory rate limiter using a sliding window.

    Keys are arbitrary strings (e.g.  ``f"{endpoint}:{ip}:{identifier}"``).
    Values are lists of epoch timestamps (float).
    """

    def __init__(self):
        self._store: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def _clean_window(self, timestamps: List[float], window_seconds: int) -> List[float]:
        """Remove timestamps older than the sliding window."""
        cutoff = time.time() - window_seconds
        return [ts for ts in timestamps if ts > cutoff]

    def is_allowed(self, key: str, rule: RateLimitRule) -> bool:
        """
        Check whether a request under *key* is allowed under *rule*.
        Returns ``True`` if allowed, ``False`` if the limit has been exceeded.
        """
        now = time.time()
        with self._lock:
            timestamps = self._store.get(key, [])
            timestamps = self._clean_window(timestamps, rule.window_seconds)
            if len(timestamps) >= rule.max_requests:
                self._store[key] = timestamps
                return False
            timestamps.append(now)
            self._store[key] = timestamps
            return True

    def reset(self, key: str) -> None:
        """Clear all tracked timestamps for a given key."""
        with self._lock:
            self._store.pop(key, None)

    def reset_all(self) -> None:
        """Clear the entire store. Useful in tests."""
        with self._lock:
            self._store.clear()


# Global singleton – can be replaced with a Redis-backed limiter in production
_default_limiter: Optional[InMemoryRateLimiter] = None


def get_default_limiter() -> InMemoryRateLimiter:
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = InMemoryRateLimiter()
    return _default_limiter


def set_default_limiter(limiter: InMemoryRateLimiter) -> None:
    global _default_limiter
    _default_limiter = limiter


# ---------------------------------------------------------------------------
# Dependency factories
# ---------------------------------------------------------------------------

AUTH_RULE = RateLimitRule(max_requests=5, window_seconds=300)  # 5 attempts / 5 min


def _get_client_ip(request: Request) -> str:
    """Extract the client IP from the request, honouring X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Take the first IP in the chain (closest to client)
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def rate_limit_by_ip(
    rule: RateLimitRule = AUTH_RULE,
    limiter: Optional[InMemoryRateLimiter] = None,
) -> Callable:
    """
    FastAPI dependency factory that limits requests by **client IP only**.
    """
    if limiter is None:
        limiter = get_default_limiter()

    async def _check(request: Request) -> None:
        ip = _get_client_ip(request)
        key = f"{request.url.path}:{ip}"
        if not limiter.is_allowed(key, rule):
            raise RateLimitExceeded()

    return _check


def rate_limit_by_ip_and_field(
    field_name: str,
    rule: RateLimitRule = AUTH_RULE,
    limiter: Optional[InMemoryRateLimiter] = None,
) -> Callable:
    """
    FastAPI dependency factory that limits requests by **client IP + a body field**
    (e.g. ``email`` for login or forgot-password).
    """
    if limiter is None:
        limiter = get_default_limiter()

    async def _check(request: Request) -> None:
        ip = _get_client_ip(request)
        body = await request.body()
        field_value = "unknown"
        if body:
            try:
                import json
                data = json.loads(body)
                field_value = data.get(field_name, "unknown")
            except Exception:
                pass
        # Re-inject the body so downstream consumers can still read it
        async def _receive() -> dict:
            return {"type": "http.request", "body": body}
        request._receive = _receive

        key = f"{request.url.path}:{ip}:{field_value}"
        if not limiter.is_allowed(key, rule):
            raise RateLimitExceeded()

    return _check
