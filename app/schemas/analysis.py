from pydantic import BaseModel


class ProductLink(BaseModel):
    title: str
    price: str | None = None
    url: str
    source: str
    confidence: float


class StreamingLink(BaseModel):
    title: str
    platform: str
    url: str
    type: str  # "subscription", "rent", "buy"
    confidence: float


class AnalysisResult(BaseModel):
    id: str
    description: str
    confidence: float
    category: str  # "product", "movie", "show", "restaurant", "location", "unknown"
    raw_text: str | None = None
    product_links: list[ProductLink] = []
    streaming_links: list[StreamingLink] = []
    tags: list[str] = []
    processing_time_ms: float
