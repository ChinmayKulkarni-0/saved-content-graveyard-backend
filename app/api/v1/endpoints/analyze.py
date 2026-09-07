import time

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.core.config import settings
from app.core.logging import ImageAction, log_image_event
from app.core.rate_limit import rate_limiter
from app.core.security import get_current_user
from app.schemas.analysis import AnalysisResult
from app.services.storage import storage_service
from app.services.vision import VisionService

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_BATCH_SIZE = 5


async def _validate_and_read(file: UploadFile) -> bytes:
    if not file.content_type or file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File must be one of: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )
    content = await file.read()
    if len(content) > settings.IMAGE_UPLOAD_MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum size of {settings.IMAGE_UPLOAD_MAX_SIZE_MB}MB",
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    return content


@router.post("/", response_model=AnalysisResult)
async def analyze_screenshot(
    request: Request,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
):
    await rate_limiter.check_rate_limit(request, tier="free")

    content = await _validate_and_read(file)
    filename = file.filename or "upload.png"

    log_image_event(ImageAction.VALIDATE, filename, user_id=current_user, file_size=len(content))

    tmp_path = None
    start = time.monotonic()
    try:
        tmp_path = await storage_service.save_temp_image(content, filename, user_id=current_user)

        log_image_event(ImageAction.PROCESS_START, filename, user_id=current_user)

        vision_service = VisionService()
        result = await vision_service.analyze_image(tmp_path)

        elapsed_ms = (time.monotonic() - start) * 1000
        log_image_event(
            ImageAction.PROCESS_COMPLETE,
            filename,
            user_id=current_user,
            duration_ms=elapsed_ms,
            detail=f"category={result.get('category', 'unknown')}",
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        log_image_event(
            ImageAction.PROCESS_COMPLETE,
            filename,
            user_id=current_user,
            duration_ms=elapsed_ms,
            detail=f"error={e}",
        )
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")
    finally:
        if tmp_path:
            await storage_service.delete_image(tmp_path, user_id=current_user)


@router.post("/batch", response_model=list[AnalysisResult])
async def analyze_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    current_user: str = Depends(get_current_user),
):
    await rate_limiter.check_rate_limit(request, tier="free")

    results: list[AnalysisResult] = []
    for file in files[:MAX_BATCH_SIZE]:
        try:
            content = await _validate_and_read(file)
            filename = file.filename or "upload.png"

            tmp_path = None
            try:
                tmp_path = await storage_service.save_temp_image(content, filename, user_id=current_user)

                vision_service = VisionService()
                result = await vision_service.analyze_image(tmp_path)
                results.append(result)
            finally:
                if tmp_path:
                    await storage_service.delete_image(tmp_path, user_id=current_user)
        except HTTPException:
            continue
    return results


@router.post("/cleanup")
async def trigger_cleanup():
    """Manually trigger orphan cleanup (admin/debug)."""
    removed = await storage_service.cleanup_orphans()
    return {"removed": removed, "active": storage_service.active_count}
