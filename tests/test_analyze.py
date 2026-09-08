import pytest
from fastapi.testclient import TestClient

from app.main import app


def _auth_headers():
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": "test-user"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    return TestClient(app)


class TestAnalyzeEndpoint:
    def test_rejects_unauthenticated(self, client):
        resp = client.post("/v1/analyze/", files={"file": ("test.png", b"fake", "image/png")})
        assert resp.status_code == 401

    def test_rejects_non_image(self, client):
        resp = client.post(
            "/v1/analyze/",
            files={"file": ("test.txt", b"hello", "text/plain")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert "image" in resp.json()["detail"].lower()

    def test_rejects_empty_file(self, client):
        resp = client.post(
            "/v1/analyze/",
            files={"file": ("empty.png", b"", "image/png")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_rejects_oversized_file(self, client):
        big = b"\x00" * (11 * 1024 * 1024)  # 11MB > 10MB limit
        resp = client.post(
            "/v1/analyze/",
            files={"file": ("big.png", big, "image/png")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert "size" in resp.json()["detail"].lower()

    def test_accepts_valid_image(self, client):
        fake_image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        resp = client.post(
            "/v1/analyze/",
            files={"file": ("photo.png", fake_image, "image/png")},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "type" in data
        assert "title" in data
        assert "description" in data
        assert "confidence" in data
        assert "links" in data
        assert "metadata" in data

    def test_temp_file_deleted_after_processing(self, client):
        import glob as glob_mod
        import os
        import tempfile

        before = set(glob_mod.glob(os.path.join(tempfile.gettempdir(), "scg_uploads", "*")))
        fake_image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        client.post(
            "/v1/analyze/",
            files={"file": ("photo.png", fake_image, "image/png")},
            headers=_auth_headers(),
        )
        after = set(glob_mod.glob(os.path.join(tempfile.gettempdir(), "scg_uploads", "*")))
        # No new files should remain
        assert after - before == set()


class TestBatchEndpoint:
    def test_batch_rejects_unauthenticated(self, client):
        resp = client.post(
            "/v1/analyze/batch",
            files=[("files", ("a.png", b"fake", "image/png"))],
        )
        assert resp.status_code == 401

    def test_batch_processes_multiple(self, client):
        fake = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        resp = client.post(
            "/v1/analyze/batch",
            files=[
                ("files", ("a.png", fake, "image/png")),
                ("files", ("b.png", fake, "image/png")),
            ],
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_batch_skips_invalid_files(self, client):
        fake = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        resp = client.post(
            "/v1/analyze/batch",
            files=[
                ("files", ("a.png", fake, "image/png")),
                ("files", ("b.txt", b"not an image", "text/plain")),
            ],
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestCleanupEndpoint:
    def test_cleanup_returns_stats(self, client):
        resp = client.post("/v1/analyze/cleanup", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "removed" in data
        assert "active" in data

    def test_cleanup_requires_auth(self, client):
        resp = client.post("/v1/analyze/cleanup")
        assert resp.status_code == 401
