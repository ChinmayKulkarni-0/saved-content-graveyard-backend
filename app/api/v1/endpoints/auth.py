import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import rate_limiter
from app.core.security import (
    create_access_token,
    get_current_user_model,
    get_password_hash,
    verify_password,
)
from app.db.session import get_db
from app.models.user import SavedResult as SavedResultModel
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, Token, UserCreate, UserPublic

logger = logging.getLogger(__name__)

# A constant bcrypt hash so an unknown email still pays the same hashing
# cost as a real account, mitigating user enumeration via timing.
_DUMMY_HASH = "$2b$12$VqC7KMRMKhlLza7.BN3gHuQWN6Bo4Lj6mxnMjJ.q8zQkQkD/3LOci"

EMAIL_DUPLICATE = "Email already registered"
INVALID_CREDENTIALS = "Invalid credentials"

router = APIRouter()


async def _auth_rate_limit(request: Request, namespace: str = "auth") -> None:
    await rate_limiter.check_rate_limit(
        request,
        limit=settings.RATE_LIMIT_AUTH_TRIES,
        namespace=namespace,
    )


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _authenticate_user(
    db: AsyncSession, request: Request, email: str, password: str
) -> User:
    """Look up the user and verify the password, timing-safe for unknown emails."""
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()

    stored_hash = user.hashed_password if user else _DUMMY_HASH
    if not stored_hash or not verify_password(password, stored_hash):
        logger.warning(
            "Failed login email=%r from=%s", email, _client_host(request)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning("Login refused for inactive user=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _build_auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(data={"sub": str(user.id)}),
        token_type="bearer",
        user=UserPublic.model_validate(user),
    )


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and return an access token",
)
async def signup(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await _auth_rate_limit(request, namespace="signup")

    email = payload.email.lower()
    existing = await db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=EMAIL_DUPLICATE,
        )

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        is_active=True,
        is_pro=False,
        free_usage_count=0,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        logger.warning("Signup race: email already registered %s", email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=EMAIL_DUPLICATE,
        )

    logger.info("New user created email=%s id=%s", email, user.id)
    return _build_auth_response(user)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login with email + password and return an access token",
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await _auth_rate_limit(request)
    user = await _authenticate_user(db, request, payload.email, payload.password)
    logger.info("Login success email=%s id=%s", user.email, user.id)
    return _build_auth_response(user)


@router.post("/token", response_model=Token, summary="Login (OAuth2 password flow)")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    await _auth_rate_limit(request)
    user = await _authenticate_user(db, request, form_data.username, form_data.password)
    logger.info("OAuth2 login success id=%s", user.id)
    return Token(access_token=create_access_token(data={"sub": str(user.id)}))


@router.post("/logout", summary="Logout (client-side token deletion for MVP)")
async def logout():
    """Placeholder logout. MVP clients simply discard the token locally."""
    logger.info("User initiated logout")
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserPublic, summary="Get the current user's info")
async def read_current_user(
    user: User = Depends(get_current_user_model),
):
    return UserPublic.model_validate(user)


@router.delete("/me", summary="Delete the current user's account permanently")
async def delete_current_user(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the account and every saved result card, atomically.

    SavedResult rows are removed explicitly first: the FK has no ON DELETE
    CASCADE, so they must be purged before the user row. Both statements share
    one transaction — if either fails, nothing is deleted.
    """
    try:
        await db.execute(
            delete(SavedResultModel).where(SavedResultModel.user_id == user.id)
        )
        await db.delete(user)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("Failed to delete account for user=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete the account. Please try again.",
        )
    logger.info("Deleted account id=%s email=%s", user.id, user.email)
    return {"message": "Account deleted successfully"}