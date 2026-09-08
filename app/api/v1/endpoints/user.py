from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import get_current_active_user
from app.models.user import User
from app.schemas.user import UsageResponse
from app.services.usage import FREE_MONTHLY_LIMIT, free_usage_remaining

router = APIRouter(tags=["user"])


@router.get("/usage", response_model=UsageResponse)
async def get_user_usage(
    user: Annotated[User, Depends(get_current_active_user)],
) -> UsageResponse:
    """Report the user's monthly analysis quota.

    Read-only: it never resets the counter; a rolled-over calendar month is
    reported with a fresh (full) allowance even though the stored counters
    still contain the previous period's values.
    """
    if user.is_pro:
        return UsageResponse(
            free_usage_count=user.free_usage_count or 0,
            usage_month=user.usage_month,
            usage_year=user.usage_year,
            is_pro=True,
            limit=None,
            remaining="unlimited",
        )
    return UsageResponse(
        free_usage_count=user.free_usage_count or 0,
        usage_month=user.usage_month,
        usage_year=user.usage_year,
        is_pro=False,
        limit=FREE_MONTHLY_LIMIT,
        remaining=free_usage_remaining(user),
    )