import pytest
from fastapi.testclient import TestClient

from app.main import app


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