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

PASSWORD = "secret123"
EMAIL = "newuser@example.com"
FULL_NAME = "New User"

DUMMY_ID = uuid.uuid4()


@pytest.fixture
async def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        session.add(
            User(
                id=DUMMY_ID,
                email="existing@example.com",
                hashed_password=get_password_hash(PASSWORD),
                full_name="Existing User",
            )
        )
        await session.commit()

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()
    os.unlink(path)


def _headers(sub: str | None = None):
    token = create_access_token(data={"sub": sub or str(DUMMY_ID)})
    return {"Authorization": f"Bearer {token}"}


class TestSignup:
    async def test_signup_creates_user_and_returns_token(self, client):
        resp = await client.post(
            "/v1/auth/signup",
            json={"email": EMAIL, "password": PASSWORD, "full_name": FULL_NAME},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["token_type"] == "bearer"
        assert data["access_token"]
        assert data["user"]["email"] == EMAIL
        assert data["user"]["full_name"] == FULL_NAME
        assert data["user"]["is_pro"] is False
        assert data["user"]["id"]

    async def test_signup_duplicate_email_returns_400(self, client):
        resp = await client.post(
            "/v1/auth/signup",
            json={"email": "existing@example.com", "password": PASSWORD},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Email already registered"

    async def test_signup_normalizes_email(self, client):
        resp = await client.post(
            "/v1/auth/signup",
            json={"email": "UPPER@EXAMPLE.COM", "password": PASSWORD},
        )
        assert resp.status_code == 201
        assert resp.json()["user"]["email"] == "upper@example.com"

    async def test_signup_invalid_payload_returns_422(self, client):
        resp = await client.post(
            "/v1/auth/signup",
            json={"email": "not-an-email", "password": "123"},
        )
        assert resp.status_code == 422


class TestLogin:
    async def test_login_success_returns_user_and_token(self, client):
        resp = await client.post(
            "/v1/auth/login",
            json={"email": "existing@example.com", "password": PASSWORD},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"]
        assert data["user"]["email"] == "existing@example.com"

    async def test_login_wrong_password_returns_401(self, client):
        resp = await client.post(
            "/v1/auth/login",
            json={"email": "existing@example.com", "password": "wrong-password"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    async def test_login_unknown_email_returns_401(self, client):
        resp = await client.post(
            "/v1/auth/login",
            json={"email": "nobody@example.com", "password": PASSWORD},
        )
        assert resp.status_code == 401


class TestLogout:
    async def test_logout_returns_success(self, client):
        resp = await client.post("/v1/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Successfully logged out"


class TestMe:
    async def test_me_returns_current_user(self, client):
        resp = await client.get("/v1/auth/me", headers=_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(DUMMY_ID)
        assert data["email"] == "existing@example.com"
        assert data["full_name"] == "Existing User"

    async def test_me_requires_auth(self, client):
        resp = await client.get("/v1/auth/me")
        assert resp.status_code == 401

    async def test_me_rejects_token_for_unknown_user(self, client):
        resp = await client.get("/v1/auth/me", headers=_headers(str(uuid.uuid4())))
        assert resp.status_code == 401

    async def test_me_rejects_tampered_token(self, client):
        token = create_access_token(data={"sub": str(DUMMY_ID)})
        tampered = token[:-2] + ("A" if token[-1] != "A" else "B")
        resp = await client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {tampered}"},
        )
        assert resp.status_code == 401