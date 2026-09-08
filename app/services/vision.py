import asyncio
import base64
import json
import logging

import httpx

from app.core.config import settings
from app.schemas.pipeline import ContentType, VisionAnalysis

logger = logging.getLogger(__name__)

GEMINI_VISION_PROMPT = """Analyze this screenshot. Extract all visible text (OCR) and identify what the image is about.

Return a JSON object with these fields:
- "raw_text": all text visible in the image (string or null)
- "detected_items": list of key items/products/movies/shows detected (list of strings)
- "content_type_hint": one of "product", "movie", "tv", "unknown" (string)
- "title_hint": the main product name, movie title, or show name if identifiable (string or null)
- "description": a short 1-2 sentence natural description of what the image shows (string)
- "confidence": how confident you are in the classification, 0.0 to 1.0 (float)

Rules:
- If it looks like a product listing, shopping post, or item for sale → content_type_hint = "product"
- If it looks like a movie poster, review, or streaming screen → content_type_hint = "movie"
- If it looks like a TV show, series poster, or episode screen → content_type_hint = "tv"
- Otherwise → content_type_hint = "unknown"
- Always try to extract as much text as possible via OCR
- Be concise in the description

Return ONLY valid JSON, no markdown fences."""


def _is_production() -> bool:
    return settings.APP_ENV.lower() == "production"


class VisionService:
    """Multimodal vision service using Google Gemini Flash."""

    async def analyze_image(self, image_path: str) -> VisionAnalysis:
        """Analyze an image file for OCR + content classification."""
        image_bytes = await asyncio.to_thread(self._read_file, image_path)
        mime_type = self._guess_mime_type(image_path)
        return await self._analyze_with_gemini(image_bytes, mime_type)

    async def analyze_image_bytes(self, image_bytes: bytes, mime_type: str = "image/png") -> VisionAnalysis:
        """Analyze raw image bytes for OCR + content classification."""
        return await self._analyze_with_gemini(image_bytes, mime_type)

    @staticmethod
    def _read_file(image_path: str) -> bytes:
        with open(image_path, "rb") as f:
            return f.read()

    async def _analyze_with_gemini(self, image_bytes: bytes, mime_type: str) -> VisionAnalysis:
        """Call the Gemini Flash API for multimodal analysis.

        In production, a missing key or a full model outage is an error, not a
        graceful "unknown" result. In development we fall back to empty
        analysis so the API is usable without credentials.
        """
        if not settings.GOOGLE_GEMINI_API_KEY:
            if _is_production():
                raise RuntimeError("GOOGLE_GEMINI_API_KEY is not configured (APP_ENV=production)")
            logger.warning("No Gemini API key configured, returning empty analysis")
            return VisionAnalysis()

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": GEMINI_VISION_PROMPT},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": image_b64,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
            },
        }

        headers = {"x-goog-api-key": settings.GOOGLE_GEMINI_API_KEY}

        for model in (settings.GEMINI_MODEL, settings.GEMINI_MODEL_FALLBACK):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()

                text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                    if text.endswith("```"):
                        text = text[:-3]
                    text = text.strip()

                data = json.loads(text)
                return VisionAnalysis(
                    raw_text=data.get("raw_text"),
                    detected_items=data.get("detected_items", []),
                    content_type_hint=ContentType(data.get("content_type_hint", "unknown")),
                    title_hint=data.get("title_hint"),
                    description=data.get("description", ""),
                    confidence=float(data.get("confidence", 0.5)),
                )
            except Exception as exc:
                # Log the failure class only: the exception string can embed
                # request URLs, which must never reach logs with headers attached.
                logger.warning("Gemini model %s failed: %s", model, type(exc).__name__)
                continue

        if _is_production():
            raise RuntimeError("All Gemini models failed")
        logger.error("All Gemini models failed")
        return VisionAnalysis(description="Vision analysis failed", confidence=0.0)

    @staticmethod
    def _guess_mime_type(path: str) -> str:
        lower = path.lower()
        if lower.endswith(".png"):
            return "image/png"
        if lower.endswith((".jpg", ".jpeg")):
            return "image/jpeg"
        if lower.endswith(".webp"):
            return "image/webp"
        if lower.endswith(".gif"):
            return "image/gif"
        return "image/png"