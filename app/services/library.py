"""Helpers for persisting and loading saved result cards."""

from app.models.user import SavedResult as SavedResultModel
from app.schemas.library import SavedResult
from app.schemas.pipeline import ContentType, Link


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