import os
import tempfile
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.logging import logger
from app.core.security import get_current_user
from app.schemas.analysis import AnalysisResult
from app.services.vision import VisionService

router = APIRouter()


@router.post("/", response_model=AnalysisResult)
async def analyze_screenshot(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (png, jpg, webp)",
        )

    max_bytes = settings.IMAGE_UPLOAD_MAX_SIZE_MB * 1024 * 1024
    tmp_path = None
    start = time.perf_counter()

    try:
        content = await file.read()
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum size of {settings.IMAGE_UPLOAD_MAX_SIZE_MB}MB",
            )

        suffix = os.path.splitext(file.filename or "upload.png")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        logger.info(
            "Analyzing image: %s (%d bytes) user=%s",
            file.filename,
            len(content),
            current_user,
        )

        vision_service = VisionService()
        result = await vision_service.analyze_image(tmp_path)

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "Analysis complete: category=%s confidence=%.2f %.0fms user=%s",
            result["category"],
            result["confidence"],
            elapsed,
            current_user,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Analysis failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image analysis failed. Please try again.",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/batch", response_model=list[AnalysisResult])
async def analyze_batch(
    files: list[UploadFile] = File(...),
    current_user: str = Depends(get_current_user),
):
    if len(files) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size limited to 5 files",
        )

    max_bytes = settings.IMAGE_UPLOAD_MAX_SIZE_MB * 1024 * 1024
    results = []

    for file in files:
        if not file.content_type or not file.content_type.startswith("image/"):
            continue

        content = await file.read()
        if len(content) > max_bytes:
            logger.warning("Skipping oversized file: %s", file.filename)
            continue

        tmp_path = None
        try:
            suffix = os.path.splitext(file.filename or "upload.png")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            vision_service = VisionService()
            result = await vision_service.analyze_image(tmp_path)
            results.append(result)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    logger.info("Batch analysis complete: %d/%d succeeded", len(results), len(files))
    return results
