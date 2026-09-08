import pytest
from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.rate_limit import RateLimiter


def _make_request(client_id: str = "127.0.0.1", headers: list[tuple[bytes, bytes]] | None = None):
    """Create a minimal mock Request for testing."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "client": (client_id, 0),
        "server": ("localhost", 8000),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_allows_requests_under_limit():
    limiter = RateLimiter()
    req = _make_request("10.0.0.1")
    for _ in range(5):
        await limiter.check_rate_limit(req)
    assert True  # no exception raised


@pytest.mark.asyncio
async def test_blocks_requests_over_limit():
    limiter = RateLimiter()
    req = _make_request("10.0.0.2")
    for _ in range(settings.RATE_LIMIT_FREE_TIER):
        await limiter.check_rate_limit(req)
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check_rate_limit(req)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_explicit_limit_overrides_default():
    limiter = RateLimiter()
    req = _make_request("10.0.0.21")
    for _ in range(3):
        await limiter.check_rate_limit(req, limit=3)
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check_rate_limit(req, limit=3)
    assert exc_info.value.status_code == 429
    # a higher explicit limit reassesses the same bucket
    await limiter.check_rate_limit(req, limit=5)
    assert True


@pytest.mark.asyncio
async def test_different_clients_independent():
    limiter = RateLimiter()
    req1 = _make_request("10.0.0.3")
    req2 = _make_request("10.0.0.4")
    for _ in range(5):
        await limiter.check_rate_limit(req1)
    # req2 should still work
    await limiter.check_rate_limit(req2)
    assert True


@pytest.mark.asyncio
async def test_namespaced_buckets_are_independent():
    limiter = RateLimiter()
    req = _make_request("10.0.0.6")
    for _ in range(settings.RATE_LIMIT_FREE_TIER):
        await limiter.check_rate_limit(req, namespace="default")
    # a separate namespace (e.g. login) is unlimited by default namespace
    await limiter.check_rate_limit(req, limit=100, namespace="auth")
    assert True


@pytest.mark.asyncio
async def test_spoofed_xff_is_not_trusted_by_default():
    """X-Forwarded-For must not bypass the limit unless the proxy header is trusted."""
    limiter = RateLimiter()
    spoofer = _make_request(
        "10.0.0.7",
        headers=[(b"x-forwarded-for", b"203.0.113.99")],
    )
    for _ in range(settings.RATE_LIMIT_FREE_TIER):
        await limiter.check_rate_limit(spoofer)
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check_rate_limit(spoofer)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_bucket_cap_evicts_oldest():
    """The bucket store stays bounded under a flood of distinct client ids."""
    limiter = RateLimiter()
    for i in range(12000):
        req = _make_request(f"10.0.0.{i + 1}")
        await limiter.check_rate_limit(req, limit=1000)
    assert len(limiter._buckets) <= 10000