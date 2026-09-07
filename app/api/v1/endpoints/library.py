import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import SavedItem as SavedItemModel
from app.schemas.library import SavedItem
from app.schemas.pipeline import PipelineResult
from app.services.library import from_pipeline_result, to_schema

router = APIRouter()


async def _get_owned_item(db: AsyncSession, item_id: str, user_id: str) -> SavedItemModel:
    result = await db.execute(
        select(SavedItemModel).where(
            SavedItemModel.id == item_id,
            SavedItemModel.user_id == user_id,
            SavedItemModel.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved item not found",
        )
    return item


@router.post("/", response_model=SavedItem, status_code=status.HTTP_201_CREATED)
async def save_item(
    result: PipelineResult,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save an analyzed result card to the user's library."""
    payload = from_pipeline_result(result)

    item = SavedItemModel(
        id=str(uuid.uuid4()),
        user_id=current_user,
        description=payload.description,
        category=payload.category,
        confidence=payload.confidence,
        raw_text=payload.raw_text,
        product_links_json=json.dumps(payload.product_links),
        streaming_links_json=json.dumps(payload.streaming_links),
        tags_json=json.dumps(payload.tags),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return to_schema(item)


@router.get("/", response_model=list[SavedItem])
async def get_saved_items(
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedItemModel)
        .where(
            SavedItemModel.user_id == current_user,
            SavedItemModel.is_deleted.is_(False),
        )
        .order_by(SavedItemModel.created_at.desc())
    )
    return [to_schema(item) for item in result.scalars().all()]


@router.get("/{item_id}", response_model=SavedItem)
async def get_saved_item(
    item_id: str,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await _get_owned_item(db, item_id, current_user)
    return to_schema(item)


@router.delete("/{item_id}")
async def delete_saved_item(
    item_id: str,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await _get_owned_item(db, item_id, current_user)
    item.is_deleted = True
    await db.commit()
    return {"status": "deleted"}