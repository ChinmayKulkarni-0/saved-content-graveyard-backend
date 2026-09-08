"""Authentication dependencies for protected routes.

`get_current_user` decodes the JWT and loads the user row from the DB.
`get_current_active_user` additionally gates on `is_active`.
Invalid or missing tokens -> 401; unknown user -> 404; inactive user -> 403.
"""

import logging
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import oauth2_scheme
from app.db.session import get_db
from app.models.user import User

logger = logging.getLogger(__name__)


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _user_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found",
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the JWT and return the matching user row (or raise 401/404)."""
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
    try:
        user_id = UUID(sub)
    except (ValueError, TypeError, AttributeError):
        logger.warning("JWT sub is not a valid UUID: %r", sub)
        raise _user_not_found()

    user = await db.get(User, user_id)
    if user is None:
        logger.warning("JWT issued for unknown user=%s", user_id)
        raise _user_not_found()

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require an active account (403 for deactivated users)."""
    if not current_user.is_active:
        logger.warning("Blocked inactive user=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


async def get_admin_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Require the configured admin account for sensitive operations."""
    if current_user.email != settings.ADMIN_USERNAME:
        logger.warning("Admin access denied for user=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user