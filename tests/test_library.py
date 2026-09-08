import os
import tempfile
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import Base

PIPELINE_RESULT = {
    "type": "product",
    "title": "Example Chair",
    "description": "A comfortable ergonomic chair.",
    "confidence": 0.92,
    "links": [
        {"label": "Buy on Amazon", "url": "https://amazon.com/chair", "type": "buy"},
        {"label": "More info", "url": "https://google.com/search?q=chair", "type": "info"},
    ],
    "metadata": {"raw_text": "chair product", "detected_items": ["chair"]},
}


def _headers(sub: str | None = None):
    token = create_access_token(data={"sub": sub or str(uuid.uuid4())})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

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


async def test_library_requires_auth(client):
    resp = await client.get("/v1/library/")
    assert resp.status_code == 401


async def test_requires_auth_to_save(client):
    resp = await client.post("/v1/library/", json=PIPELINE_RESULT)
    assert resp.status_code == 401


async def test_save_result_creates_saved_result(client):
    sub = str(uuid.uuid4())
    resp = await client.post("/v1/library/", json=PIPELINE_RESULT, headers=_headers(sub))
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"]
    assert data["user_id"] == sub
    assert data["type"] == "product"
    assert data["title"] == "Example Chair"
    assert data["description"] == "A comfortable ergonomic chair."
    assert data["confidence"] == 0.92
    assert data["links"] == [
        {"label": "Buy on Amazon", "url": "https://amazon.com/chair", "type": "buy"},
        {"label": "More info", "url": "https://google.com/search?q=chair", "type": "info"},
    ]
    assert data["metadata"] == {"raw_text": "chair product", "detected_items": ["chair"]}
    assert data["thumbnail_url"] is None
    assert data["created_at"]
    assert data["updated_at"]


async def test_save_and_list(client):
    sub = str(uuid.uuid4())
    created = await client.post("/v1/library/", json=PIPELINE_RESULT, headers=_headers(sub))
    item_id = created.json()["id"]

    listed = await client.get("/v1/library/", headers=_headers(sub))
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == item_id


async def test_library_is_user_scoped(client):
    other_headers = {"Authorization": f"Bearer {create_access_token(data={'sub': str(uuid.uuid4())})}"}
    await client.post("/v1/library/", json=PIPELINE_RESULT, headers=_headers())

    listed = await client.get("/v1/library/", headers=other_headers)
    assert listed.json() == []


async def test_get_single_item(client):
    sub = str(uuid.uuid4())
    created = await client.post("/v1/library/", json=PIPELINE_RESULT, headers=_headers(sub))
    item_id = created.json()["id"]

    resp = await client.get(f"/v1/library/{item_id}", headers=_headers(sub))
    assert resp.status_code == 200
    assert resp.json()["id"] == item_id


async def test_get_missing_item_returns_404(client):
    resp = await client.get("/v1/library/00000000-0000-0000-0000-000000000000", headers=_headers())
    assert resp.status_code == 404


async def test_invalid_item_id_returns_422(client):
    resp = await client.get("/v1/library/not-a-uuid", headers=_headers())
    assert resp.status_code == 422


async def test_cannot_read_another_users_item(client):
    created = await client.post("/v1/library/", json=PIPELINE_RESULT, headers=_headers())
    item_id = created.json()["id"]

    other_headers = {"Authorization": f"Bearer {create_access_token(data={'sub': str(uuid.uuid4())})}"}
    resp = await client.get(f"/v1/library/{item_id}", headers=other_headers)
    assert resp.status_code == 404


async def test_delete_removes_item(client):
    sub = str(uuid.uuid4())
    created = await client.post("/v1/library/", json=PIPELINE_RESULT, headers=_headers(sub))
    item_id = created.json()["id"]

    deleted = await client.delete(f"/v1/library/{item_id}", headers=_headers(sub))
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted"}

    listed = await client.get("/v1/library/", headers=_headers(sub))
    assert listed.json() == []
    assert (await client.get(f"/v1/library/{item_id}", headers=_headers(sub))).status_code == 404
    assert (await client.delete(f"/v1/library/{item_id}", headers=_headers(sub))).status_code == 404