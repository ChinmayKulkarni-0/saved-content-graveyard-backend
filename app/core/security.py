import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT. The algorithm is pinned to HS256, preventing key confusion."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    """Validate the bearer token and return the user id encoded in `sub`.

    This is a pure JWT check (no DB round-trip) and is safe to use for
    cheap authorization gates and logging. Use `get_current_user_model`
    when you need the user row or its profile.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        logger.warning("Rejected invalid JWT")
        raise _credentials_exception()

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        logger.warning("Rejected JWT without a valid sub claim")
        raise _credentials_exception()
    return sub


async def get_current_user_model(
    user_id: Annotated[str, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate the token and return the active User row (or 401)."""
    try:
        user_uuid = UUID(user_id)
    except (ValueError, TypeError, AttributeError):
        logger.warning("JWT sub is not a valid UUID: %r", user_id)
        raise _credentials_exception()

    user = await db.get(User, user_uuid)
    if user is None or not user.is_active:
        logger.warning("JWT issued for unknown/inactive user=%s", user_uuid)
        raise _credentials_exception()
    return user


async def get_admin_user(user: Annotated[User, Depends(get_current_user_model)]) -> User:
    """Require the configured admin account for sensitive operations."""
    if user.email != settings.ADMIN_USERNAME:
        logger.warning("Admin access denied for user=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user