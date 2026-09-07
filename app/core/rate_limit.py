import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.core.config import settings


class RateLimiter:
    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_id(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def check_rate_limit(self, request: Request, tier: str = "free"):
        client_id = self._get_client_id(request)
        now = time.time()
        window = 60.0

        limit = (
            settings.RATE_LIMIT_PRO_TIER
            if tier == "pro"
            else settings.RATE_LIMIT_FREE_TIER
        )

        self._requests[client_id] = [
            t for t in self._requests[client_id] if now - t < window
        ]

        if len(self._requests[client_id]) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
            )

        self._requests[client_id].append(now)


rate_limiter = RateLimiter()
