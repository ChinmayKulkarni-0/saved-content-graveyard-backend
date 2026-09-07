"""Helpers for persisting and loading saved result cards."""

import json

from app.models.user import SavedItem as SavedItemModel
from app.schemas.library import SavedItem, SavedItemCreate
from app.schemas.pipeline import LinkType, PipelineResult


def from_pipeline_result(result: PipelineResult) -> SavedItemCreate:
    """Build a saved-item payload from an analyzed screenshot result."""
    product_links: list = []
    streaming_links: list = []
    for link in result.links:
        if link.type == LinkType.BUY:
            product_links.append(
                {
                    "title": link.label,
                    "url": link.url,
                    "source": "unknown",
                    "confidence": result.confidence,
                }
            )
        elif link.type == LinkType.STREAM:
            streaming_links.append(
                {
                    "title": link.label,
                    "platform": "unknown",
                    "url": link.url,
                    "type": "subscription",
                    "confidence": result.confidence,
                }
            )

    metadata = result.metadata or {}
    return SavedItemCreate(
        description=result.description,
        category=result.type.value,
        confidence=result.confidence,
        raw_text=metadata.get("raw_text"),
        product_links=product_links,
        streaming_links=streaming_links,
        tags=metadata.get("detected_items", []),
    )


def to_schema(item: SavedItemModel) -> SavedItem:
    """Convert a database row to its API schema."""
    return SavedItem(
        id=item.id,
        user_id=item.user_id,
        description=item.description,
        category=item.category,
        confidence=item.confidence,
        raw_text=item.raw_text,
        product_links=json.loads(item.product_links_json or "[]"),
        streaming_links=json.loads(item.streaming_links_json or "[]"),
        tags=json.loads(item.tags_json or "[]"),
        created_at=item.created_at,
        is_deleted=item.is_deleted,
    )