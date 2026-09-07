from datetime import datetime

from pydantic import BaseModel


class SavedItem(BaseModel):
    id: str
    user_id: str
    description: str
    category: str
    confidence: float
    raw_text: str | None = None
    product_links: list = []
    streaming_links: list = []
    tags: list[str] = []
    created_at: datetime
    is_deleted: bool = False
