from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    PRODUCT = "product"
    MOVIE = "movie"
    TV = "tv"
    UNKNOWN = "unknown"


class LinkType(str, Enum):
    BUY = "buy"
    STREAM = "stream"
    INFO = "info"


class Link(BaseModel):
    label: str
    url: str
    type: LinkType


class PipelineResult(BaseModel):
    type: ContentType
    title: str
    description: str = Field(description="Short natural description, 1-2 sentences")
    confidence: float = Field(ge=0.0, le=1.0)
    links: list[Link] = []
    metadata: dict = {}


class AnalyzeResponse(PipelineResult):
    """Pipeline result plus the id of the card persisted to the user's library."""

    saved_id: UUID


class VisionAnalysis(BaseModel):
    raw_text: str | None = None
    detected_items: list[str] = []
    content_type_hint: ContentType = ContentType.UNKNOWN
    title_hint: str | None = None
    description: str = ""
    confidence: float = 0.0
