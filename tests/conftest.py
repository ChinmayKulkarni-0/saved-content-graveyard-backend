import os

import pytest

from app.core.config import settings
from app.core.rate_limit import rate_limiter
from app.services.storage import storage_service


@pytest.fixture(autouse=True)
def _no_external_api(monkeypatch):
    """Keep the suite offline and deterministic: never call vision/production APIs."""
    monkeypatch.setattr(settings, "GOOGLE_GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Isolate tests from the global in-memory rate limiter and storage tracker."""
    rate_limiter._buckets.clear()
    storage_service._active.clear()
    yield
    rate_limiter._buckets.clear()
    storage_service._active.clear()