import time

from fastapi import HTTPException, Request, status

from app.core.config import settings

DEFAULT_WINDOW_SECONDS = 60.0
MAX_BUCKETS = 10_000


class RateLimiter:
    """In-memory sliding-window rate limiter.

    Buckets live in a single process: deploy behind a single worker, or swap
    for a shared store (e.g. Redis) when scaling out. The client id comes
    from the direct peer by default; X-Forwarded-For is only trusted when
    TRUST_X_FORWARDED_FOR is enabled (i.e. behind a known proxy), otherwise
    clients can trivially spoof it to bypass limits.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = {}

    def _client_id(self, request: Request) -> str:
        if settings.TRUST_X_FORWARDED_FOR:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                ip = forwarded.split(",")[0].strip()
                if ip:
                    return ip
        return request.client.host if request.client else "unknown"

    def _prune(self, now: float) -> None:
        if len(self._buckets) < MAX_BUCKETS:
            return
        stale = [
            key
            for key, hits in self._buckets.items()
            if not hits or now - hits[-1] >= DEFAULT_WINDOW_SECONDS
        ]
        for key in stale:
            del self._buckets[key]

    async def check_rate_limit(
        self,
        request: Request,
        limit: int | None = None,
        window: float = DEFAULT_WINDOW_SECONDS,
        namespace: str = "default",
    ) -> None:
        """Register one request; raise 429 once `limit` is exceeded in `window`."""
        effective_limit = (
            limit if limit is not None else settings.RATE_LIMIT_FREE_TIER
        )
        key = f"{namespace}:{self._client_id(request)}"

        now = time.monotonic()
        hits = [t for t in self._buckets.get(key, ()) if now - t < window]
        if len(hits) >= effective_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
            )
        hits.append(now)
        self._buckets[key] = hits
        self._prune(now)


rate_limiter = RateLimiter()