import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.services.storage import storage_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

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
    _cleanup_task = asyncio.create_task(_periodic_cleanup())
    yield
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

app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}
