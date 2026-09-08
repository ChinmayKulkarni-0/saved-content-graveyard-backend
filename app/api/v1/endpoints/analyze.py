import time

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.core.config import settings
from app.core.logging import ImageAction, log_image_event, logger
from app.core.rate_limit import rate_limiter
from app.core.security import get_current_user
from app.schemas.pipeline import PipelineResult
from app.services.pipeline import ProcessingPipeline
from app.services.storage import storage_service

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_BATCH_SIZE = 5


async def _validate_and_read(file: UploadFile) -> bytes:
    if not file.content_type or file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File must be one of: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )
    content = await file.read()
    if len(content) > settings.IMAGE_UPLOAD_MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum size of {settings.IMAGE_UPLOAD_MAX_SIZE_MB}MB",
        )
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")
    return content


@router.post("/", response_model=PipelineResult)
async def analyze_screenshot(
    request: Request,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
):
    # TODO: resolve user tier (is_pro) and use RATE_LIMIT_PRO_TIER for pro users.
    await rate_limiter.check_rate_limit(request, limit=settings.RATE_LIMIT_FREE_TIER)

    content = await _validate_and_read(file)
    filename = file.filename or "upload.png"

    log_image_event(ImageAction.VALIDATE, filename, user_id=current_user, file_size=len(content))

    tmp_path = None
    start = time.perf_counter()
    try:
        tmp_path = await storage_service.save_temp_image(content, filename, user_id=current_user)

        log_image_event(ImageAction.PROCESS_START, filename, user_id=current_user)

        pipeline = ProcessingPipeline()
        result = await pipeline.process_image(tmp_path)

        elapsed_ms = (time.perf_counter() - start) * 1000
        log_image_event(
            ImageAction.PROCESS_COMPLETE,
            filename,
            user_id=current_user,
            duration_ms=elapsed_ms,
            detail=f"type={result.type.value}",
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log_image_event(
            ImageAction.PROCESS_COMPLETE,
            filename,
            user_id=current_user,
            duration_ms=elapsed_ms,
            detail=f"error={e}",
        )
        logger.error("Analysis failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image analysis failed. Please try again.",
        )
    finally:
        if tmp_path:
            await storage_service.delete_image(tmp_path, user_id=current_user)


@router.post("/batch", response_model=list[PipelineResult])
async def analyze_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    current_user: str = Depends(get_current_user),
):
    await rate_limiter.check_rate_limit(request, limit=settings.RATE_LIMIT_FREE_TIER)

    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size limited to {MAX_BATCH_SIZE} files",
        )

    results: list[PipelineResult] = []
    for file in files:
        try:
            content = await _validate_and_read(file)
            filename = file.filename or "upload.png"

            tmp_path = None
            try:
                tmp_path = await storage_service.save_temp_image(content, filename, user_id=current_user)

                pipeline = ProcessingPipeline()
                result = await pipeline.process_image(tmp_path)
                results.append(result)
            finally:
                if tmp_path:
                    await storage_service.delete_image(tmp_path, user_id=current_user)
        except HTTPException:
            continue

    logger.info("Batch analysis complete: %d/%d succeeded", len(results), len(files))
    return results


@router.post("/cleanup", summary="Trigger manual orphan-file cleanup (debug)")
async def trigger_cleanup(_current_user: str = Depends(get_current_user)):
    """Manually trigger orphan cleanup (auth required)."""
    removed = await storage_service.cleanup_orphans()
    return {"removed": removed, "active": storage_service.active_count}
