"""Monthly freemium usage quota for the analyze endpoints.

Free users get ``FREE_MONTHLY_LIMIT`` analyses per calendar month (UTC).
Pro users have no monthly cap; counting still happens so the number is
visible in ``GET /user/usage``. Persisting happens via the caller's session:
``enforce_free_monthly_quota`` flushes a rolling-month reset, and
``increment_free_usage`` commits the new count.
"""

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

FREE_MONTHLY_LIMIT = 10
FREE_LIMIT_MESSAGE = "Free limit reached. Upgrade to Pro."


def current_period() -> tuple[int, int]:
    """Return the current calendar (month, year) in UTC."""
    now = datetime.utcnow()
    return now.month, now.year


def effective_count(user: User) -> int:
    """Return the usable monthly count, treating a rolled-over period as zero."""
    month, year = current_period()
    if user.usage_month != month or user.usage_year != year:
        return 0
    return user.free_usage_count or 0


def free_usage_remaining(user: User) -> int:
    return max(0, FREE_MONTHLY_LIMIT - effective_count(user))


async def enforce_free_monthly_quota(user: User, db: AsyncSession) -> None:
    """Reset the counter when the calendar month rolled over, then gate the request.

    Raises ``403`` with a frontend-friendly ``detail`` (``message``, ``limit``,
    ``remaining``) once a free user has exhausted the monthly allowance. The
    check runs before any image is read or processed.
    """
    month, year = current_period()

    if user.usage_month != month or user.usage_year != year:
        user.free_usage_count = 0
        user.usage_month = month
        user.usage_year = year
        await db.flush()
        return

    if not user.is_pro and effective_count(user) >= FREE_MONTHLY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": FREE_LIMIT_MESSAGE,
                "limit": FREE_MONTHLY_LIMIT,
                "remaining": 0,
            },
        )


async def increment_free_usage(user: User, db: AsyncSession, count: int = 1) -> None:
    """Bump the monthly counter after successful analyses and persist it."""
    month, year = current_period()
    if user.usage_month != month or user.usage_year != year:
        user.free_usage_count = count
        user.usage_month = month
        user.usage_year = year
    else:
        user.free_usage_count = (user.free_usage_count or 0) + count
    await db.commit()