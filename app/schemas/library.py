import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.pipeline import ContentType, Link


class SavedResult(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: ContentType
    title: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    links: list[Link] = []
    metadata: dict = {}
    thumbnail_url: str | None = None
    created_at: datetime
    updated_at: datetime