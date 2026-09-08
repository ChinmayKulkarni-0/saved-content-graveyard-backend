import os
import tempfile
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import Base, User


def _health_headers(uid: uuid.UUID):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(uid)})}"}


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "ok"


def test_health_reports_degraded_when_db_down(monkeypatch):
    class _BrokenConn:
        async def __aenter__(self):
            raise RuntimeError("db unreachable")

        async def __aexit__(self, *exc):
            return False

    class _DownDB:
        def connect(self):
            return _BrokenConn()

    monkeypatch.setattr("app.main.engine", _DownDB())

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "degraded"
    assert response.json()["detail"]["database"] == "unavailable"


def test_security_headers_present():
    client = TestClient(app)
    response = client.get("/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "no-referrer"


@pytest.fixture
async def auth_client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    active_id = uuid.uuid4()
    inactive_id = uuid.uuid4()

    async with maker() as session:
        session.add_all(
            [
                User(id=active_id, email="active@example.com", hashed_password="x"),
                User(
                    id=inactive_id,
                    email="inactive@example.com",
                    hashed_password="x",
                    is_active=False,
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
        c.active_id = active_id
        c.inactive_id = inactive_id
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()
    os.unlink(path)


class TestHealthAuthRoute:
    async def test_requires_token(self, auth_client):
        resp = await auth_client.get("/health/auth")
        assert resp.status_code == 401

    async def test_returns_active_user(self, auth_client):
        resp = await auth_client.get("/health/auth", headers=_health_headers(auth_client.active_id))
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["user_id"] == str(auth_client.active_id)
        assert data["email"] == "active@example.com"

    async def test_forbids_inactive_user(self, auth_client):
        resp = await auth_client.get("/health/auth", headers=_health_headers(auth_client.inactive_id))
        assert resp.status_code == 403

    async def test_unknown_user_returns_404(self, auth_client):
        resp = await auth_client.get("/health/auth", headers=_health_headers(uuid.uuid4()))
        assert resp.status_code == 404