"""Helpers for persisting and loading saved result cards."""

import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import SavedResult as SavedResultModel
from app.models.user import User
from app.schemas.library import SavedResult
from app.schemas.pipeline import ContentType, Link, PipelineResult


def to_schema(item: SavedResultModel) -> SavedResult:
    """Convert a database row to its API schema."""
    return SavedResult(
        id=item.id,
        user_id=item.user_id,
        type=ContentType(item.type or ContentType.UNKNOWN.value),
        title=item.title or "",
        description=item.description or "",
        confidence=item.confidence or 0.0,
        links=[Link(**link) for link in (item.links or [])],
        metadata=item.metadata_json or {},
        thumbnail_url=item.thumbnail_url,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def save_result(
    db: AsyncSession,
    user: User,
    result: PipelineResult,
    thumbnail_url: str | None = None,
) -> SavedResultModel:
    """Persist a PipelineResult card for the user and commit it.

    Raises the original SQLAlchemyError on failure after rolling back.
    """
    item = SavedResultModel(
        id=uuid.uuid4(),
        user_id=user.id,
        type=result.type.value,
        title=result.title,
        description=result.description,
        confidence=result.confidence,
        links=[link.model_dump() for link in result.links],
        metadata_json=result.metadata,
        thumbnail_url=thumbnail_url,
    )
    try:
        db.add(item)
        await db.commit()
        await db.refresh(item)
    except SQLAlchemyError:
        await db.rollback()
        raise
    return item