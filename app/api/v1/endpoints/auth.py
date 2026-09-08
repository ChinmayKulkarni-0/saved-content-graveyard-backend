import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import rate_limiter
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import Token

logger = logging.getLogger(__name__)

# A constant bcrypt hash so an unknown username still pays the same hashing
# cost as a real account, mitigating username enumeration via timing.
_DUMMY_HASH = "$2b$12$VqC7KMRMKhlLza7.BN3gHuQWN6Bo4Lj6mxnMjJ.q8zQkQkD/3LOci"

router = APIRouter()


@router.post("/token", response_model=Token, summary="Login (OAuth2 password flow)")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    await rate_limiter.check_rate_limit(
        request, limit=settings.RATE_LIMIT_AUTH_TRIES, namespace="auth"
    )

    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    stored_hash = user.hashed_password if user else _DUMMY_HASH
    if not stored_hash or not verify_password(form_data.password, stored_hash):
        logger.warning(
            "Failed login for username=%r from=%s",
            form_data.username,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning("Login refused for inactive user=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    logger.info("Login success user=%s", user.id)
    return Token(access_token=access_token, token_type="bearer")