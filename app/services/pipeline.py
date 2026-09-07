import logging
import time

from app.schemas.pipeline import ContentType, Link, LinkType, PipelineResult, VisionAnalysis
from app.services.movie import MovieService
from app.services.product import ProductService
from app.services.vision import VisionService

logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """AI processing pipeline: image → vision analysis → structured result."""

    def __init__(self) -> None:
        self.vision = VisionService()
        self.product_service = ProductService()
        self.movie_service = MovieService()

    async def process_image(self, image_path: str) -> PipelineResult:
        """Full pipeline: analyze image → classify → find links → return structured result."""
        start = time.monotonic()

        vision_result = await self.vision.analyze_image(image_path)

        content_type = self._classify_content(vision_result)
        title = self._extract_title(vision_result)

        links = await self._resolve_links(content_type, title, vision_result)

        elapsed_ms = (time.monotonic() - start) * 1000

        return PipelineResult(
            type=content_type,
            title=title or "Unknown",
            description=vision_result.description or "Could not analyze the image",
            confidence=vision_result.confidence,
            links=links,
            metadata={
                "raw_text": vision_result.raw_text,
                "detected_items": vision_result.detected_items,
                "processing_time_ms": round(elapsed_ms, 1),
            },
        )

    def _classify_content(self, vision: VisionAnalysis) -> ContentType:
        """Determine content type from vision analysis."""
        if vision.confidence >= 0.7 and vision.content_type_hint != ContentType.UNKNOWN:
            return vision.content_type_hint

        combined = " ".join([vision.title_hint or "", vision.description, *vision.detected_items]).lower()

        product_keywords = ["buy", "price", "shop", "product", "cart", "add to", "sale", "discount", "size"]
        movie_keywords = ["movie", "film", "trailer", "cinema", "theater", "streaming", "release"]
        tv_keywords = ["season", "episode", "series", "show", "netflix", "hulu", "hbo", "watch"]

        product_score = sum(1 for kw in product_keywords if kw in combined)
        movie_score = sum(1 for kw in movie_keywords if kw in combined)
        tv_score = sum(1 for kw in tv_keywords if kw in combined)

        scores = [
            (ContentType.PRODUCT, product_score),
            (ContentType.MOVIE, movie_score),
            (ContentType.TV, tv_score),
        ]
        best = max(scores, key=lambda x: x[1])

        if best[1] > 0:
            return best[0]

        return ContentType.UNKNOWN

    def _extract_title(self, vision: VisionAnalysis) -> str | None:
        """Extract the most likely title from vision results."""
        if vision.title_hint:
            return vision.title_hint

        if vision.detected_items:
            return vision.detected_items[0]

        if vision.raw_text:
            first_line = vision.raw_text.strip().split("\n")[0].strip()
            if 2 < len(first_line) < 100:
                return first_line

        return None

    async def _resolve_links(
        self,
        content_type: ContentType,
        title: str | None,
        vision: VisionAnalysis,
    ) -> list[Link]:
        """Find relevant links based on content type."""
        if content_type == ContentType.PRODUCT:
            return await self.product_service.find_buy_links(title, vision.description, vision.detected_items)

        if content_type in (ContentType.MOVIE, ContentType.TV):
            return await self.movie_service.find_streaming_links(
                title, vision.description, vision.detected_items, content_type
            )

        links: list[Link] = []
        if title:
            encoded = title.replace(" ", "+")
            links.append(
                Link(
                    label=f"Search for '{title}'",
                    url=f"https://google.com/search?q={encoded}",
                    type=LinkType.INFO,
                )
            )
        return links
