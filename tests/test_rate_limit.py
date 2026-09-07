import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app.core.rate_limit import RateLimiter
from app.main import app


def _make_request(client_id: str = "127.0.0.1"):
    """Create a minimal mock Request for testing."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": (client_id, 0),
        "server": ("localhost", 8000),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_allows_requests_under_limit():
    limiter = RateLimiter()
    req = _make_request("10.0.0.1")
    for _ in range(5):
        await limiter.check_rate_limit(req, tier="free")
    assert True  # no exception raised


@pytest.mark.asyncio
async def test_blocks_requests_over_limit():
    from app.core.config import settings

    limiter = RateLimiter()
    req = _make_request("10.0.0.2")
    for _ in range(settings.RATE_LIMIT_FREE_TIER):
        await limiter.check_rate_limit(req, tier="free")
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check_rate_limit(req, tier="free")
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_different_clients_independent():
    limiter = RateLimiter()
    req1 = _make_request("10.0.0.3")
    req2 = _make_request("10.0.0.4")
    for _ in range(5):
        await limiter.check_rate_limit(req1, tier="free")
    # req2 should still work
    await limiter.check_rate_limit(req2, tier="free")
    assert True


@pytest.mark.asyncio
async def test_pro_tier_higher_limit():
    from app.core.config import settings

    limiter = RateLimiter()
    req = _make_request("10.0.0.5")
    for _ in range(settings.RATE_LIMIT_FREE_TIER + 1):
        await limiter.check_rate_limit(req, tier="pro")
    assert True  # pro tier allows more


class TestRateLimitIntegration:
    def test_rate_limit_returns_429(self):
        client = TestClient(app)
        from app.core.security import create_access_token

        token = create_access_token(data={"sub": "rl-test"})
        headers = {"Authorization": f"Bearer {token}"}
        fake = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

        from app.core.config import settings

        for _ in range(settings.RATE_LIMIT_FREE_TIER + 1):
            client.post(
                "/v1/analyze/",
                files={"file": ("p.png", fake, "image/png")},
                headers=headers,
            )
        resp = client.post(
            "/v1/analyze/",
            files={"file": ("p.png", fake, "image/png")},
            headers=headers,
        )
        assert resp.status_code == 429
