"""Async database engine, session factory, and FastAPI dependency."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import logger
from app.models.user import Base


def _async_url(url: str) -> str:
    """Map a sync SQLAlchemy URL to its async driver."""
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(
    _async_url(settings.DATABASE_URL),
    echo=False,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables on startup.

    Dev/test-friendly only. In production (APP_ENV=production) startup does
    nothing here — schema is managed by Alembic migrations instead.
    """
    if settings.APP_ENV.lower() == "production":
        return

    logger.warning("create_all is running (APP_ENV=%s) — use Alembic in production", settings.APP_ENV)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an async session per request."""
    async with async_session_maker() as session:
        yield session