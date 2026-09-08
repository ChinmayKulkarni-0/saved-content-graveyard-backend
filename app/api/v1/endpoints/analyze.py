import time

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_active_user
from app.core.logging import ImageAction, log_image_event, logger
from app.core.rate_limit import rate_limiter
from app.core.security import get_admin_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.pipeline import AnalyzeResponse, PipelineResult
from app.services.library import save_result
from app.services.pipeline import ProcessingPipeline
from app.services.storage import storage_service

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_BATCH_SIZE = 5


def _detect_mime(content: bytes) -> str | None:
    """Return the mime type for a validated image, or None if not an image."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x52\x49\x46\x46") and content[8:12] == b"WEBP":
        return "image/webp"
    return None


_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

_LIMIT_BY_TIER = {
    "free": "RATE_LIMIT_FREE_TIER",
    "pro": "RATE_LIMIT_PRO_TIER",
}


async def _read_and_validate(file: UploadFile) -> tuple[bytes, str]:
    """Read the upload with a hard size cap and validate it is a real image."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File must be one of: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )

    max_bytes = settings.IMAGE_UPLOAD_MAX_SIZE_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)  # +1 byte to detect over-limit reads
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum size of {settings.IMAGE_UPLOAD_MAX_SIZE_MB}MB",
        )
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")

    mime = _detect_mime(content)
    if mime is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a valid image",
        )
    return content, mime


async def _apply_rate_limit(request: Request, user: User) -> None:
    limit_name = _LIMIT_BY_TIER["pro" if user.is_pro else "free"]
    await rate_limiter.check_rate_limit(request, limit=getattr(settings, limit_name))


@router.post("/", response_model=AnalyzeResponse)
async def analyze_screenshot(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _apply_rate_limit(request, user)

    content, mime = await _read_and_validate(file)
    filename = file.filename or "upload"
    stored_name = f"upload{_EXT_BY_MIME[mime]}"

    log_image_event(ImageAction.VALIDATE, filename, user_id=str(user.id), file_size=len(content))

    tmp_path = None
    start = time.perf_counter()
    try:
        tmp_path = await storage_service.save_temp_image(content, stored_name, user_id=str(user.id))

        log_image_event(ImageAction.PROCESS_START, filename, user_id=str(user.id))

        pipeline = ProcessingPipeline()
        result = await pipeline.process_image(tmp_path)

        try:
            saved = await save_result(db, user, result)
        except SQLAlchemyError:
            logger.exception("Failed to persist analysis result for user=%s", user.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Image analysis failed. Please try again.",
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        log_image_event(
            ImageAction.PROCESS_COMPLETE,
            filename,
            user_id=str(user.id),
            duration_ms=elapsed_ms,
            detail=f"type={result.type.value} saved_id={saved.id}",
        )
        return AnalyzeResponse(saved_id=saved.id, **result.model_dump())

    except HTTPException:
        raise
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log_image_event(
            ImageAction.PROCESS_COMPLETE,
            filename,
            user_id=str(user.id),
            duration_ms=elapsed_ms,
            detail=f"error={type(e).__name__}",
        )
        logger.error("Analysis failed for user=%s: %s", user.id, type(e).__name__, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image analysis failed. Please try again.",
        )
    finally:
        if tmp_path:
            deleted = await storage_service.delete_image(tmp_path, user_id=str(user.id))
            if not deleted:
                logger.warning("Failed to delete temp image %s for user=%s", tmp_path, user.id)


@router.post("/batch", response_model=list[PipelineResult])
async def analyze_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_active_user),
):
    await _apply_rate_limit(request, user)

    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size limited to {MAX_BATCH_SIZE} files",
        )

    results: list[PipelineResult] = []
    for file in files:
        filename = file.filename or "upload"
        try:
            content, mime = await _read_and_validate(file)
            stored_name = f"upload{_EXT_BY_MIME[mime]}"
            tmp_path = await storage_service.save_temp_image(content, stored_name, user_id=str(user.id))

            try:
                pipeline = ProcessingPipeline()
                results.append(await pipeline.process_image(tmp_path))
            finally:
                deleted = await storage_service.delete_image(tmp_path, user_id=str(user.id))
                if not deleted:
                    logger.warning("Failed to delete temp image %s for user=%s", tmp_path, user.id)
        except HTTPException as exc:
            logger.info("Batch skipped invalid file %r: %s", filename, exc.detail)
            continue
        except Exception:
            logger.exception("Batch file %r failed for user=%s", filename, user.id)
            continue

    logger.info(
        "Batch analysis complete for user=%s: %d/%d succeeded",
        user.id,
        len(results),
        len(files),
    )
    return results


@router.post(
    "/cleanup",
    summary="Trigger manual orphan-file cleanup (admin only)",
    dependencies=[Depends(get_admin_user)],
)
async def trigger_cleanup():
    """Manually trigger orphan cleanup (admin only)."""
    removed = await storage_service.cleanup_orphans()
    return {"removed": removed, "active": storage_service.active_count}