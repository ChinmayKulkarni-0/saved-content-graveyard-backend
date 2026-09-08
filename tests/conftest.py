import os

import pytest

from app.core.rate_limit import rate_limiter
from app.services.storage import storage_service


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Isolate tests from the global in-memory rate limiter and storage tracker."""
    rate_limiter._buckets.clear()
    storage_service._active.clear()
    yield
    rate_limiter._buckets.clear()
    storage_service._active.clear()