"""Seed default users so the API is usable out of the box."""

import logging
import uuid

from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import async_session_maker
from app.models.user import User

logger = logging.getLogger(__name__)

DUMMY_USER_EMAIL = "dummy@example.com"
DUMMY_USER_PASSWORD = "password123"


async def seed_default_users() -> None:
    """Create the admin (from settings) plus a dummy user if no users exist."""
    async with async_session_maker() as session:
        count = (
            await session.execute(select(func.count()).select_from(User))
        ).scalar_one()
        if count > 0:
            return

        admin = User(
            id=uuid.uuid4(),
            email=settings.ADMIN_USERNAME,
            hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
            full_name="Admin",
            is_pro=True,
        )
        dummy = User(
            id=uuid.uuid4(),
            email=DUMMY_USER_EMAIL,
            hashed_password=get_password_hash(DUMMY_USER_PASSWORD),
            full_name="Dummy User",
        )
        session.add_all([admin, dummy])
        await session.commit()

        logger.info(
            "Seeded default users: admin=%s dummy=%s",
            settings.ADMIN_USERNAME,
            DUMMY_USER_EMAIL,
        )