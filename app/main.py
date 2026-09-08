import asyncio
import logging
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.deps import get_current_active_user
from app.core.logging import logger, setup_logging
from app.db.seed import seed_default_users
from app.db.session import engine, init_db
from app.models.user import User
from app.services.storage import storage_service

_cleanup_task: asyncio.Task | None = None
_cleanup_logger = logging.getLogger("cleanup")


async def _periodic_cleanup():
    while True:
        try:
            await storage_service.cleanup_orphans()
        except Exception as exc:
            _cleanup_logger.warning("Cleanup cycle failed: %s", exc)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task
    setup_logging()
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    await init_db()
    await seed_default_users()
    _cleanup_task = asyncio.create_task(_periodic_cleanup())
    yield
    logger.info("Shutting down %s", settings.APP_NAME)
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception: %s %s -> %s\n%s",
        request.method,
        request.url.path,
        exc,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )


@app.middleware("http")
async def add_security_headers(_request: Request, call_next):
    response = await call_next(_request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    return response


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    process_time = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time:.1f}"
    return response


app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health_check():
    """Liveness probe: app is up and the database answers a trivial query."""
    try:
        async with asyncio.timeout(2):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Health check: database unreachable", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "version": settings.APP_VERSION,
                "database": "unavailable",
            },
        )
    return {"status": "healthy", "version": settings.APP_VERSION, "database": "ok"}


@app.get("/health/auth", tags=["health"], summary="Protected route probe")
async def health_auth(user: User = Depends(get_current_active_user)):
    """Canary: proves the auth dependency + DB round-trip work end to end."""
    return {"status": "ok", "user_id": str(user.id), "email": user.email}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
