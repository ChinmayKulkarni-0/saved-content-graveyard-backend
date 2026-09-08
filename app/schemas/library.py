import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.pipeline import ContentType, Link


class SavedResult(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: ContentType
    title: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    links: list[Link] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    thumbnail_url: str | None = None
    created_at: datetime
    updated_at: datetime


class SavedResultCreate(BaseModel):
    """Request body for manually saving a result card (no AI pipeline involved)."""

    type: ContentType
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=5000)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    links: list[Link] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    thumbnail_url: str | None = None

    @field_validator("title", "description")
    @classmethod
    def _strip_and_reject_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SavedResultList(BaseModel):
    """Paginated list of the user's saved result cards."""

    count: int
    limit: int
    offset: int
    results: list[SavedResult]
