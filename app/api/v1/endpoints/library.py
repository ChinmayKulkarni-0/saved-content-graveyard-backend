import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import SavedResult as SavedResultModel
from app.models.user import User
from app.schemas.library import SavedResult
from app.schemas.pipeline import PipelineResult
from app.services.library import to_schema

logger = logging.getLogger(__name__)

router = APIRouter()


async def _require_user(db: AsyncSession, current_user: str) -> uuid.UUID:
    try:
        user_id = uuid.UUID(current_user)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user_id


async def _get_owned_result(
    db: AsyncSession, item_id: uuid.UUID, user_id: uuid.UUID
) -> SavedResultModel:
    result = await db.execute(
        select(SavedResultModel).where(
            SavedResultModel.id == item_id,
            SavedResultModel.user_id == user_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved result not found",
        )
    return item


@router.post("/", response_model=SavedResult, status_code=status.HTTP_201_CREATED)
async def save_result(
    result: PipelineResult,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save an analyzed result card to the user's library."""
    user_id = await _require_user(db, current_user)

    item = SavedResultModel(
        id=uuid.uuid4(),
        user_id=user_id,
        type=result.type.value,
        title=result.title,
        description=result.description,
        confidence=result.confidence,
        links=[link.model_dump() for link in result.links],
        metadata_json=result.metadata,
    )
    try:
        db.add(item)
        await db.commit()
        await db.refresh(item)
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("Failed to save result for user=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save the result.",
        )
    logger.info("Saved result %s for user=%s", item.id, user_id)
    return to_schema(item)


@router.get("/", response_model=list[SavedResult])
async def get_saved_results(
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's saved result cards, newest first."""
    user_id = await _require_user(db, current_user)

    result = await db.execute(
        select(SavedResultModel)
        .where(SavedResultModel.user_id == user_id)
        .order_by(SavedResultModel.created_at.desc())
    )
    return [to_schema(item) for item in result.scalars().all()]


@router.get("/{item_id}", response_model=SavedResult)
async def get_saved_result(
    item_id: uuid.UUID,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a single saved result owned by the current user."""
    item = await _get_owned_result(db, item_id, await _require_user(db, current_user))
    return to_schema(item)


@router.delete("/{item_id}", summary="Delete a saved result (hard delete)")
async def delete_saved_result(
    item_id: uuid.UUID,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hard-delete a single saved result owned by the current user."""
    user_id = await _require_user(db, current_user)
    item = await _get_owned_result(db, item_id, user_id)
    try:
        await db.delete(item)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("Failed to delete result %s for user=%s", item_id, user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete the saved result.",
        )
    logger.info("Deleted result %s for user=%s", item_id, user_id)
    return {"status": "deleted"}