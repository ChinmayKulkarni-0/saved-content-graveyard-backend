import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import SavedResult as SavedResultModel
from app.schemas.library import SavedResult
from app.schemas.pipeline import PipelineResult
from app.services.library import to_schema

router = APIRouter()


def _parse_user_id(current_user: str) -> uuid.UUID:
    try:
        return uuid.UUID(current_user)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )


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
    user_id = _parse_user_id(current_user)

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
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return to_schema(item)


@router.get("/", response_model=list[SavedResult])
async def get_saved_results(
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = _parse_user_id(current_user)

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
    item = await _get_owned_result(db, item_id, _parse_user_id(current_user))
    return to_schema(item)


@router.delete("/{item_id}")
async def delete_saved_result(
    item_id: uuid.UUID,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await _get_owned_result(db, item_id, _parse_user_id(current_user))
    await db.delete(item)
    await db.commit()
    return {"status": "deleted"}