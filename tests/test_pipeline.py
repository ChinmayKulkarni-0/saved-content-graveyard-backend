from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.pipeline import ContentType, LinkType, PipelineResult, VisionAnalysis
from app.services.pipeline import ProcessingPipeline


def _make_vision_result(
    description: str = "A product listing for boots",
    content_type: ContentType = ContentType.PRODUCT,
    title_hint: str | None = "Dr. Martens Boots",
    confidence: float = 0.85,
    raw_text: str | None = "Dr. Martens 1460 Pascal",
    detected_items: list[str] | None = None,
) -> VisionAnalysis:
    if detected_items is None:
        detected_items = ["Dr. Martens", "boots"]
    return VisionAnalysis(
        raw_text=raw_text,
        detected_items=detected_items,
        content_type_hint=content_type,
        title_hint=title_hint,
        description=description,
        confidence=confidence,
    )


class TestPipelineResultModel:
    def test_pipeline_result_serialization(self):
        result = PipelineResult(
            type=ContentType.PRODUCT,
            title="Test Product",
            description="A test product",
            confidence=0.9,
            links=[],
            metadata={},
        )
        data = result.model_dump()
        assert data["type"] == "product"
        assert data["title"] == "Test Product"
        assert data["confidence"] == 0.9

    def test_pipeline_result_confidence_bounds(self):
        with pytest.raises(Exception):
            PipelineResult(
                type=ContentType.UNKNOWN,
                title="X",
                description="X",
                confidence=1.5,
            )

    def test_empty_links_default(self):
        result = PipelineResult(
            type=ContentType.UNKNOWN,
            title="X",
            description="X",
            confidence=0.5,
        )
        assert result.links == []
        assert result.metadata == {}


class TestProcessingPipeline:
    @pytest.mark.asyncio
    async def test_process_image_returns_structured_result(self, tmp_path):
        pipeline = ProcessingPipeline()
        vision_result = _make_vision_result()

        fake_image = tmp_path / "test.png"
        fake_image.write_bytes(b"fake-png-data")

        with patch.object(pipeline.vision, "analyze_image", new_callable=AsyncMock, return_value=vision_result):
            result = await pipeline.process_image(str(fake_image))

        assert isinstance(result, PipelineResult)
        assert result.type == ContentType.PRODUCT
        assert result.title == "Dr. Martens Boots"
        assert result.confidence == 0.85
        assert result.metadata["processing_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_classify_content_product(self):
        pipeline = ProcessingPipeline()
        vision = _make_vision_result(content_type=ContentType.PRODUCT, confidence=0.9)
        assert pipeline._classify_content(vision) == ContentType.PRODUCT

    @pytest.mark.asyncio
    async def test_classify_content_movie(self):
        pipeline = ProcessingPipeline()
        vision = _make_vision_result(
            content_type=ContentType.MOVIE,
            description="A movie poster for Dune",
            confidence=0.9,
        )
        assert pipeline._classify_content(vision) == ContentType.MOVIE

    @pytest.mark.asyncio
    async def test_classify_content_fallback_keyword(self):
        pipeline = ProcessingPipeline()
        vision = VisionAnalysis(
            description="Watch the latest season of Stranger Things",
            content_type_hint=ContentType.UNKNOWN,
            confidence=0.3,
        )
        result = pipeline._classify_content(vision)
        assert result == ContentType.TV

    @pytest.mark.asyncio
    async def test_classify_content_unknown(self):
        pipeline = ProcessingPipeline()
        vision = VisionAnalysis(
            description="A random image with no clear content",
            content_type_hint=ContentType.UNKNOWN,
            confidence=0.1,
        )
        result = pipeline._classify_content(vision)
        assert result == ContentType.UNKNOWN

    @pytest.mark.asyncio
    async def test_extract_title_from_hint(self):
        pipeline = ProcessingPipeline()
        vision = _make_vision_result(title_hint="My Product")
        assert pipeline._extract_title(vision) == "My Product"

    @pytest.mark.asyncio
    async def test_extract_title_from_detected_items(self):
        pipeline = ProcessingPipeline()
        vision = _make_vision_result(title_hint=None, detected_items=["Item A", "Item B"])
        assert pipeline._extract_title(vision) == "Item A"

    @pytest.mark.asyncio
    async def test_extract_title_from_raw_text(self):
        pipeline = ProcessingPipeline()
        vision = _make_vision_result(title_hint=None, detected_items=[], raw_text="Short Title\nMore text here")
        assert pipeline._extract_title(vision) == "Short Title"

    @pytest.mark.asyncio
    async def test_extract_title_none_when_empty(self):
        pipeline = ProcessingPipeline()
        vision = _make_vision_result(title_hint=None, detected_items=[], raw_text=None)
        assert pipeline._extract_title(vision) is None


class TestProductService:
    @pytest.mark.asyncio
    async def test_find_buy_links_known_product(self):
        from app.services.product import ProductService

        service = ProductService()
        links = await service.find_buy_links("Dr. Martens boots", "some description", [])
        assert len(links) > 0
        assert links[0].type == LinkType.BUY
        assert "Amazon" in links[0].label

    @pytest.mark.asyncio
    async def test_find_buy_links_unknown_product(self):
        from app.services.product import ProductService

        service = ProductService()
        links = await service.find_buy_links("Some Random Thing", "description", [])
        assert len(links) == 1
        assert "Search for" in links[0].label

    @pytest.mark.asyncio
    async def test_find_buy_links_no_title(self):
        from app.services.product import ProductService

        service = ProductService()
        links = await service.find_buy_links(None, "description", [])
        assert len(links) == 0


class TestMovieService:
    @pytest.mark.asyncio
    async def test_find_streaming_links_known_movie(self):
        from app.services.movie import MovieService

        service = MovieService()
        links = await service.find_streaming_links("Dune", "movie poster", [], ContentType.MOVIE)
        assert len(links) > 0
        assert any(l.type == LinkType.STREAM for l in links)

    @pytest.mark.asyncio
    async def test_find_streaming_links_unknown_movie(self):
        from app.services.movie import MovieService

        service = MovieService()
        links = await service.find_streaming_links("Random Film", "description", [], ContentType.MOVIE)
        assert len(links) == 1
        assert "JustWatch" in links[0].label

    @pytest.mark.asyncio
    async def test_find_streaming_links_no_title(self):
        from app.services.movie import MovieService

        service = MovieService()
        links = await service.find_streaming_links(None, "description", [], ContentType.MOVIE)
        assert len(links) == 0
