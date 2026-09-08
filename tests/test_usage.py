import os
import tempfile
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.user import Base, User
from app.services.usage import current_period

PASSWORD = "password123"
FREE_USER = uuid.uuid4()
PRO_USER = uuid.uuid4()
INACTIVE_USER = uuid.uuid4()

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50


def _make_user(
    id_: uuid.UUID,
    email: str,
    *,
    is_pro: bool = False,
    is_active: bool = True,
    free_usage_count: int = 0,
    usage_month: int | None = 0,
    usage_year: int | None = 0,
) -> User:
    return User(
        id=id_,
        email=email,
        hashed_password=get_password_hash(PASSWORD),
        full_name="Test User",
        is_pro=is_pro,
        is_active=is_active,
        free_usage_count=free_usage_count,
        usage_month=usage_month,
        usage_year=usage_year,
    )


@pytest.fixture
async def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    month, year = current_period()
    async with maker() as session:
        session.add_all(
            [
                _make_user(FREE_USER, "free@example.com"),
                _make_user(PRO_USER, "pro@example.com", is_pro=True),
                _make_user(INACTIVE_USER, "inactive@example.com", is_active=False),
                _make_user(
                    uuid.uuid4(),
                    "at-limit@example.com",
                    free_usage_count=10,
                    usage_month=month,
                    usage_year=year,
                ),
            ]
        )
        await session.commit()

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.maker = maker
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()
    os.unlink(path)


def _headers(uid: uuid.UUID):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(uid)})}"}


def _file():
    return {"file": ("photo.png", PNG_BYTES, "image/png")}


async def _set_user(client, uid: uuid.UUID, **fields) -> None:
    async with client.maker() as session:
        user = await session.get(User, uid)
        for key, value in fields.items():
            setattr(user, key, value)
        await session.commit()


class TestUsageEndpoint:
    async def test_requires_auth(self, client):
        resp = await client.get("/v1/user/usage")
        assert resp.status_code == 401

    async def test_unknown_user_gets_404(self, client):
        resp = await client.get("/v1/user/usage", headers=_headers(uuid.uuid4()))
        assert resp.status_code == 404

    async def test_inactive_user_gets_403(self, client):
        resp = await client.get("/v1/user/usage", headers=_headers(INACTIVE_USER))
        assert resp.status_code == 403

    async def test_free_user_shape(self, client):
        resp = await client.get("/v1/user/usage", headers=_headers(FREE_USER))
        assert resp.status_code == 200
        assert resp.json() == {
            "free_usage_count": 0,
            "usage_month": 0,
            "usage_year": 0,
            "is_pro": False,
            "limit": 10,
            "remaining": 10,
        }

    async def test_pro_user_shape(self, client):
        resp = await client.get("/v1/user/usage", headers=_headers(PRO_USER))
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_pro"] is True
        assert data["limit"] is None
        assert data["remaining"] == "unlimited"

    async def test_rolled_over_month_reports_fresh_allowance(self, client):
        month, year = current_period()
        await _set_user(
            client,
            FREE_USER,
            free_usage_count=10,
            usage_month=month,
            usage_year=year - 1,
        )
        resp = await client.get("/v1/user/usage", headers=_headers(FREE_USER))
        assert resp.status_code == 200
        assert resp.json()["remaining"] == 10


class TestAnalyzeQuota:
    async def test_analyze_succeeds_within_limit(self, client):
        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(FREE_USER))
        assert resp.status_code == 200

        usage = await client.get("/v1/user/usage", headers=_headers(FREE_USER))
        assert usage.json()["free_usage_count"] == 1
        assert usage.json()["remaining"] == 9

    async def test_free_user_blocked_at_limit(self, client):
        month, year = current_period()
        await _set_user(
            client,
            FREE_USER,
            free_usage_count=10,
            usage_month=month,
            usage_year=year,
        )
        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(FREE_USER))
        assert resp.status_code == 403
        assert resp.json()["detail"] == {
            "message": "Free limit reached. Upgrade to Pro.",
            "limit": 10,
            "remaining": 0,
        }

    async def test_blocked_request_does_not_persist_card(self, client):
        month, year = current_period()
        await _set_user(
            client,
            FREE_USER,
            free_usage_count=10,
            usage_month=month,
            usage_year=year,
        )
        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(FREE_USER))
        assert resp.status_code == 403

        library = await client.get("/v1/library/", headers=_headers(FREE_USER))
        assert library.json()["count"] == 0

    async def test_pro_user_not_blocked_at_limit(self, client):
        month, year = current_period()
        await _set_user(
            client,
            PRO_USER,
            free_usage_count=10,
            usage_month=month,
            usage_year=year,
        )
        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(PRO_USER))
        assert resp.status_code == 200

        usage = await client.get("/v1/user/usage", headers=_headers(PRO_USER))
        assert usage.json()["free_usage_count"] == 11
        assert usage.json()["remaining"] == "unlimited"

    async def test_month_rollover_resets_and_allows_analysis(self, client):
        month, year = current_period()
        await _set_user(
            client,
            FREE_USER,
            free_usage_count=10,
            usage_month=month,
            usage_year=year - 1,
        )
        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(FREE_USER))
        assert resp.status_code == 200

        usage = await client.get("/v1/user/usage", headers=_headers(FREE_USER))
        assert usage.json()["free_usage_count"] == 1
        assert usage.json()["usage_month"] == month
        assert usage.json()["usage_year"] == year
        assert usage.json()["remaining"] == 9


class TestBatchQuota:
    async def test_batch_increments_per_successful_file(self, client):
        month, year = current_period()
        await _set_user(
            client,
            FREE_USER,
            free_usage_count=8,
            usage_month=month,
            usage_year=year,
        )
        resp = await client.post(
            "/v1/analyze/batch",
            files=[
                ("files", ("a.png", PNG_BYTES, "image/png")),
                ("files", ("b.txt", b"not an image", "text/plain")),
                ("files", ("c.png", PNG_BYTES, "image/png")),
            ],
            headers=_headers(FREE_USER),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        usage = await client.get("/v1/user/usage", headers=_headers(FREE_USER))
        assert usage.json()["free_usage_count"] == 10
        assert usage.json()["remaining"] == 0

    async def test_batch_blocked_before_processing_at_limit(self, client):
        month, year = current_period()
        await _set_user(
            client,
            FREE_USER,
            free_usage_count=10,
            usage_month=month,
            usage_year=year,
        )
        resp = await client.post(
            "/v1/analyze/batch",
            files=[("files", ("a.png", PNG_BYTES, "image/png"))],
            headers=_headers(FREE_USER),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["remaining"] == 0

        library = await client.get("/v1/library/", headers=_headers(FREE_USER))
        assert library.json()["count"] == 0