import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user
from app.db.session import get_db
from app.models.user import SavedResult as SavedResultModel
from app.models.user import User
from app.schemas.library import SavedResult, SavedResultCreate, SavedResultList
from app.schemas.pipeline import PipelineResult
from app.services.library import save_result as persist_result
from app.services.library import to_schema

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_owned_result(
    db: AsyncSession, item_id: uuid.UUID, user_id: uuid.UUID
) -> SavedResultModel:
    """Fetch a card owned by the user or raise 404 (no cross-user leaks)."""
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
    payload: SavedResultCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually save a result card (no AI pipeline) to the current user's library."""
    result = PipelineResult(
        type=payload.type,
        title=payload.title,
        description=payload.description,
        confidence=payload.confidence,
        links=payload.links,
        metadata=payload.metadata,
    )
    try:
        item = await persist_result(
            db, user, result, thumbnail_url=payload.thumbnail_url
        )
    except SQLAlchemyError:
        logger.exception("Failed to save result for user=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save the result.",
        )
    logger.info("Saved result %s for user=%s", item.id, user.id)
    return to_schema(item)


@router.get("/", response_model=SavedResultList)
async def get_saved_results(
    response: Response,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max items to return"),
):
    """List the current user's saved result cards, newest first."""
    total = await db.scalar(
        select(func.count()).select_from(SavedResultModel).where(
            SavedResultModel.user_id == user.id
        )
    )
    result = await db.execute(
        select(SavedResultModel)
        .where(SavedResultModel.user_id == user.id)
        .order_by(SavedResultModel.created_at.desc(), SavedResultModel.id.desc())
        .offset(offset)
        .limit(limit)
    )
    response.headers["X-Total-Count"] = str(total)
    results = [to_schema(item) for item in result.scalars().all()]
    return SavedResultList(
        count=total,
        limit=limit,
        offset=offset,
        results=results,
    )


@router.get("/{item_id}", response_model=SavedResult)
async def get_saved_result(
    item_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a single saved result owned by the current user."""
    item = await _get_owned_result(db, item_id, user.id)
    return to_schema(item)


@router.delete("/{item_id}", summary="Delete a saved result (hard delete)")
async def delete_saved_result(
    item_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Hard-delete a single saved result owned by the current user."""
    item = await _get_owned_result(db, item_id, user.id)
    try:
        await db.delete(item)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("Failed to delete result %s for user=%s", item_id, user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete the saved result.",
        )
    logger.info("Deleted result %s for user=%s", item_id, user.id)
    return {"message": "Result deleted successfully"}
