import os
import time
from pathlib import Path

import pytest

from app.services.storage import MAX_ORPHAN_AGE_SECONDS, StorageService


@pytest.fixture
def storage(tmp_path, monkeypatch):
    svc = StorageService()
    monkeypatch.setattr(svc, "_tmp_dir", tmp_path)
    return svc


@pytest.mark.asyncio
async def test_save_and_delete(storage, tmp_path):
    path = await storage.save_temp_image(b"fake png data", "test.png", user_id="u1")
    assert os.path.exists(path)
    assert path.startswith(str(tmp_path))

    deleted = await storage.delete_image(path, user_id="u1")
    assert deleted is True
    assert not os.path.exists(path)
    assert storage.active_count == 0


@pytest.mark.asyncio
async def test_delete_nonexistent(storage):
    deleted = await storage.delete_image("/tmp/no_such_file_abc123.png")
    assert deleted is True  # no error, already gone


@pytest.mark.asyncio
async def test_save_preserves_content(storage):
    data = b"\x89PNG\r\n\x1a\n" + os.urandom(100)
    path = await storage.save_temp_image(data, "photo.png")
    assert Path(path).read_bytes() == data
    await storage.delete_image(path)


@pytest.mark.asyncio
async def test_cleanup_removes_old_files(storage, monkeypatch):
    path = await storage.save_temp_image(b"old data", "old.png")
    # Artificially age the file
    storage._active[path] = time.time() - MAX_ORPHAN_AGE_SECONDS - 10

    removed = await storage.cleanup_orphans()
    assert removed >= 1
    assert not os.path.exists(path)
    assert storage.active_count == 0


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_files(storage):
    path = await storage.save_temp_image(b"fresh data", "fresh.png")
    removed = await storage.cleanup_orphans()
    assert removed == 0
    assert os.path.exists(path)
    await storage.delete_image(path)


@pytest.mark.asyncio
async def test_active_count(storage):
    assert storage.active_count == 0
    p1 = await storage.save_temp_image(b"a", "a.png")
    assert storage.active_count == 1
    p2 = await storage.save_temp_image(b"b", "b.png")
    assert storage.active_count == 2
    await storage.delete_image(p1)
    assert storage.active_count == 1
    await storage.delete_image(p2)
    assert storage.active_count == 0


@pytest.mark.asyncio
async def test_saves_to_custom_directory(tmp_path, monkeypatch):
    nested = tmp_path / "subdir"
    nested.mkdir()
    svc = StorageService()
    monkeypatch.setattr(svc, "_tmp_dir", nested)
    path = await svc.save_temp_image(b"data", "x.png")
    assert path.startswith(str(nested))
    await svc.delete_image(path)
