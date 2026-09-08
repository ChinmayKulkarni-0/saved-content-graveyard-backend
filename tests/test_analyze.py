import os
import tempfile
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.user import Base, User
from app.services.storage import storage_service

PASSWORD = "password123"

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50


def _make_user(id_: uuid.UUID, email: str, *, is_pro: bool = False, is_active: bool = True) -> User:
    return User(
        id=id_,
        email=email,
        hashed_password=get_password_hash(PASSWORD),
        full_name="Test User",
        is_pro=is_pro,
        is_active=is_active,
    )


@pytest.fixture
async def client():
    """Isolated SQLite DB with a normal user, a pro user, an admin, and an
    inactive user; routes requests through the real app via ASGITransport."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    npm = uuid.uuid4()
    pro = uuid.uuid4()
    admin = uuid.uuid4()
    inactive = uuid.uuid4()

    async with maker() as session:
        session.add_all(
            [
                _make_user(npm, "user@example.com"),
                _make_user(pro, "pro@example.com", is_pro=True),
                _make_user(admin, settings.ADMIN_USERNAME),
                _make_user(inactive, "inactive@example.com", is_active=False),
            ]
        )
        await session.commit()

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.normal_user = npm
        c.pro_user = pro
        c.admin_user = admin
        c.inactive_user = inactive
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()
    os.unlink(path)


def _headers(uid: uuid.UUID):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(uid)})}"}


def _file():
    return {"file": ("photo.png", PNG_BYTES, "image/png")}


def test_log_image_event_does_not_raise():
    """Regression: log_image_event must not use reserved LogRecord keys (e.g. filename)."""
    import logging

    from app.core.logging import ImageAction, image_lifecycle_logger, log_image_event

    prev_level = image_lifecycle_logger.level
    image_lifecycle_logger.setLevel(logging.DEBUG)
    try:
        log_image_event(ImageAction.VALIDATE, "photo.png", user_id="u1")
    finally:
        image_lifecycle_logger.setLevel(prev_level)


class TestAnalyzeEndpoint:
    async def test_rejects_unauthenticated(self, client):
        resp = await client.post("/v1/analyze/", files=_file())
        assert resp.status_code == 401

    async def test_rejects_inactive_user(self, client):
        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(client.inactive_user))
        assert resp.status_code == 403

    async def test_rejects_unknown_user(self, client):
        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(uuid.uuid4()))
        assert resp.status_code == 404

    async def test_rejects_missing_token(self, client):
        resp = await client.post("/v1/analyze/", files=_file())
        assert resp.status_code == 401

    async def test_persists_result_and_returns_saved_id(self, client):
        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(client.normal_user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved_id"]
        assert data["type"]
        assert data["confidence"] >= 0.0

        listed = await client.get("/v1/library/", headers=_headers(client.normal_user))
        assert listed.status_code == 200
        assert any(item["id"] == data["saved_id"] for item in listed.json()["results"])

    async def test_persisted_result_is_user_scoped(self, client):
        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(client.normal_user))
        saved_id = resp.json()["saved_id"]

        listed = await client.get("/v1/library/", headers=_headers(client.pro_user))
        assert all(item["id"] != saved_id for item in listed.json()["results"])

    async def test_rejects_non_image(self, client):
        resp = await client.post(
            "/v1/analyze/",
            files={"file": ("test.txt", b"hello", "text/plain")},
            headers=_headers(client.normal_user),
        )
        assert resp.status_code == 400
        assert "image" in resp.json()["detail"].lower()

    async def test_rejects_lossy_magic_bytes(self, client):
        """A fake bytes blob must not pass just because the declared type is png."""
        resp = await client.post(
            "/v1/analyze/",
            files={"file": ("evil.png", b"\x00" * 50, "image/png")},
            headers=_headers(client.normal_user),
        )
        assert resp.status_code == 400
        assert "not a valid image" in resp.json()["detail"].lower()

    async def test_rejects_gif(self, client):
        resp = await client.post(
            "/v1/analyze/",
            files={"file": ("anim.gif", b"GIF89a" + b"\x00" * 50, "image/gif")},
            headers=_headers(client.normal_user),
        )
        assert resp.status_code == 400

    async def test_rejects_empty_file(self, client):
        resp = await client.post(
            "/v1/analyze/",
            files={"file": ("empty.png", b"", "image/png")},
            headers=_headers(client.normal_user),
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    async def test_rejects_oversized_file(self, client):
        big = b"\x00" * (11 * 1024 * 1024)
        resp = await client.post(
            "/v1/analyze/",
            files={"file": ("big.png", big, "image/png")},
            headers=_headers(client.normal_user),
        )
        assert resp.status_code == 400
        assert "size" in resp.json()["detail"].lower()

    async def test_accepts_valid_image(self, client):
        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(client.normal_user))
        assert resp.status_code == 200
        data = resp.json()
        for key in ("type", "title", "description", "confidence", "links", "metadata"):
            assert key in data

    async def test_tmp_file_deleted_after_happy_path(self, client):
        tmp_dir = settings.IMAGE_TEMP_DIR
        before = {os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)}

        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(client.normal_user))
        assert resp.status_code == 200

        after = {os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)}
        assert after - before == set()

    async def test_tmp_file_deleted_even_on_pipeline_failure(self, client, monkeypatch):
        tmp_dir = settings.IMAGE_TEMP_DIR
        before = {os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)}

        from app.services.pipeline import ProcessingPipeline

        async def _boom(self, path):
            raise RuntimeError("boom")
        monkeypatch.setattr(ProcessingPipeline, "process_image", _boom)

        resp = await client.post("/v1/analyze/", files=_file(), headers=_headers(client.normal_user))
        assert resp.status_code == 500

        after = {os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)}
        assert after - before == set()


class TestBatchEndpoint:
    async def test_batch_rejects_unauthenticated(self, client):
        resp = await client.post(
            "/v1/analyze/batch",
            files=[("files", ("a.png", PNG_BYTES, "image/png"))],
        )
        assert resp.status_code == 401

    async def test_batch_rejects_more_than_five(self, client):
        files = [("files", (f"{i}.png", PNG_BYTES, "image/png")) for i in range(6)]
        resp = await client.post(
            "/v1/analyze/batch",
            files=files,
            headers=_headers(client.normal_user),
        )
        assert resp.status_code == 400

    async def test_batch_processes_multiple(self, client):
        resp = await client.post(
            "/v1/analyze/batch",
            files=[
                ("files", ("a.png", PNG_BYTES, "image/png")),
                ("files", ("b.png", PNG_BYTES, "image/png")),
            ],
            headers=_headers(client.normal_user),
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 2
        assert all(item["saved_id"] for item in items)

    async def test_batch_persists_saved_results(self, client):
        resp = await client.post(
            "/v1/analyze/batch",
            files=[("files", ("a.png", PNG_BYTES, "image/png"))],
            headers=_headers(client.normal_user),
        )
        saved_ids = {item["saved_id"] for item in resp.json()}
        assert saved_ids

        listed = await client.get("/v1/library/", headers=_headers(client.normal_user))
        assert listed.status_code == 200
        listed_ids = {item["id"] for item in listed.json()["results"]}
        assert saved_ids.issubset(listed_ids)

    async def test_batch_results_are_user_scoped(self, client):
        resp = await client.post(
            "/v1/analyze/batch",
            files=[("files", ("a.png", PNG_BYTES, "image/png"))],
            headers=_headers(client.normal_user),
        )
        saved_id = resp.json()[0]["saved_id"]

        listed = await client.get("/v1/library/", headers=_headers(client.pro_user))
        assert all(item["id"] != saved_id for item in listed.json()["results"])

    async def test_batch_skips_invalid_files(self, client):
        resp = await client.post(
            "/v1/analyze/batch",
            files=[
                ("files", ("a.png", PNG_BYTES, "image/png")),
                ("files", ("b.txt", b"not an image", "text/plain")),
            ],
            headers=_headers(client.normal_user),
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["saved_id"]


class TestCleanupEndpoint:
    async def test_cleanup_requires_auth(self, client):
        resp = await client.post("/v1/analyze/cleanup")
        assert resp.status_code == 401

    async def test_cleanup_forbidden_for_regular_user(self, client):
        resp = await client.post("/v1/analyze/cleanup", headers=_headers(client.normal_user))
        assert resp.status_code == 403

    async def test_cleanup_allowed_for_admin(self, client):
        resp = await client.post("/v1/analyze/cleanup", headers=_headers(client.admin_user))
        assert resp.status_code == 200
        data = resp.json()
        assert "removed" in data
        assert "active" in data


class TestRateLimitTiering:
    async def test_free_user_is_rate_limited(self, client):
        from app.core.config import settings as s

        headers = _headers(client.normal_user)
        for _ in range(s.RATE_LIMIT_FREE_TIER):
            resp = await client.post("/v1/analyze/", files=_file(), headers=headers)
            assert resp.status_code in (200, 429)
        resp = await client.post("/v1/analyze/", files=_file(), headers=headers)
        assert resp.status_code == 429

    async def test_pro_user_has_higher_limit(self, client):
        from app.core.config import settings as s

        headers = _headers(client.pro_user)
        for _ in range(s.RATE_LIMIT_FREE_TIER + 1):
            resp = await client.post("/v1/analyze/", files=_file(), headers=headers)
            assert resp.status_code in (200, 429)
            if resp.status_code == 429:
                break
        # pro tier must survive well past the free-tier limit without a 429
        assert resp.status_code == 200