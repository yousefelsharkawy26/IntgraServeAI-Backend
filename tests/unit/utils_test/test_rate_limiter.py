import pytest
import time
from unittest.mock import MagicMock

from fastapi import Request, status
from pydantic import BaseModel

from utils.rate_limiter import (
    InMemoryRateLimiter,
    RateLimitRule,
    RateLimitExceeded,
    rate_limit_by_ip,
    rate_limit_by_ip_and_field,
    get_default_limiter,
    set_default_limiter,
)


@pytest.fixture(autouse=True)
def reset_limiter():
    """Reset the global limiter before each test."""
    set_default_limiter(InMemoryRateLimiter())


class TestInMemoryRateLimiter:
    def test_single_request_allowed(self):
        limiter = InMemoryRateLimiter()
        rule = RateLimitRule(max_requests=5, window_seconds=60)
        assert limiter.is_allowed("key", rule) is True

    def test_exact_limit_allowed(self):
        limiter = InMemoryRateLimiter()
        rule = RateLimitRule(max_requests=3, window_seconds=60)
        assert limiter.is_allowed("key", rule) is True
        assert limiter.is_allowed("key", rule) is True
        assert limiter.is_allowed("key", rule) is True
        assert limiter.is_allowed("key", rule) is False

    def test_different_keys_isolated(self):
        limiter = InMemoryRateLimiter()
        rule = RateLimitRule(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("key_a", rule) is True
        assert limiter.is_allowed("key_b", rule) is True

    def test_window_expires(self):
        limiter = InMemoryRateLimiter()
        rule = RateLimitRule(max_requests=1, window_seconds=0)
        # With window_seconds=0, all previous timestamps are immediately expired.
        assert limiter.is_allowed("key", rule) is True
        assert limiter.is_allowed("key", rule) is True

    def test_reset_key(self):
        limiter = InMemoryRateLimiter()
        rule = RateLimitRule(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("key", rule) is True
        assert limiter.is_allowed("key", rule) is False
        limiter.reset("key")
        assert limiter.is_allowed("key", rule) is True

    def test_reset_all(self):
        limiter = InMemoryRateLimiter()
        rule = RateLimitRule(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("key_a", rule) is True
        assert limiter.is_allowed("key_b", rule) is True
        limiter.reset_all()
        assert limiter.is_allowed("key_a", rule) is True
        assert limiter.is_allowed("key_b", rule) is True


class TestRateLimitByIp:
    @pytest.mark.asyncio
    async def test_allowed_when_under_limit(self):
        check = rate_limit_by_ip(
            rule=RateLimitRule(max_requests=5, window_seconds=60)
        )
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/auth/login"
        request.headers = {}
        request.client.host = "127.0.0.1"
        # Should not raise
        await check(request)

    @pytest.mark.asyncio
    async def test_blocked_when_over_limit(self):
        rule = RateLimitRule(max_requests=2, window_seconds=60)
        check = rate_limit_by_ip(rule=rule)
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/auth/login"
        request.headers = {}
        request.client.host = "127.0.0.1"

        await check(request)
        await check(request)
        with pytest.raises(RateLimitExceeded) as exc_info:
            await check(request)
        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    @pytest.mark.asyncio
    async def test_uses_x_forwarded_for(self):
        check = rate_limit_by_ip(
            rule=RateLimitRule(max_requests=1, window_seconds=60)
        )
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/auth/login"
        request.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
        request.client.host = "127.0.0.1"

        await check(request)
        with pytest.raises(RateLimitExceeded):
            await check(request)


class TestRateLimitByIpAndField:
    @pytest.mark.asyncio
    async def test_allowed_when_under_limit(self):
        check = rate_limit_by_ip_and_field(
            "email",
            rule=RateLimitRule(max_requests=5, window_seconds=60)
        )
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/auth/login"
        request.headers = {}
        request.client.host = "127.0.0.1"

        async def _body():
            return b'{"email": "test@example.com"}'
        request.body = _body

        await check(request)

    @pytest.mark.asyncio
    async def test_blocked_when_over_limit_same_email(self):
        rule = RateLimitRule(max_requests=2, window_seconds=60)
        check = rate_limit_by_ip_and_field("email", rule=rule)
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/auth/login"
        request.headers = {}
        request.client.host = "127.0.0.1"

        async def _body():
            return b'{"email": "test@example.com"}'
        request.body = _body

        await check(request)
        await check(request)
        with pytest.raises(RateLimitExceeded):
            await check(request)

    @pytest.mark.asyncio
    async def test_different_email_not_blocked(self):
        rule = RateLimitRule(max_requests=1, window_seconds=60)
        check = rate_limit_by_ip_and_field("email", rule=rule)
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/auth/login"
        request.headers = {}
        request.client.host = "127.0.0.1"

        # First email
        async def _body_a():
            return b'{"email": "a@example.com"}'
        request.body = _body_a
        await check(request)

        with pytest.raises(RateLimitExceeded):
            await check(request)

        # Different email on same IP
        async def _body_b():
            return b'{"email": "b@example.com"}'
        request.body = _body_b
        await check(request)  # Should not raise for different email
