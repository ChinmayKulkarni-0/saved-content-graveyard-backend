import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.config import settings
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
        raise HTTPException(status_code=400, detail="File must be an image")

    file_size = 0
    tmp_path = None

    try:
        content = await file.read()
        file_size = len(content)

        if file_size > settings.IMAGE_UPLOAD_MAX_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"File exceeds maximum size of {settings.IMAGE_UPLOAD_MAX_SIZE_MB}MB",
            )

        suffix = os.path.splitext(file.filename or "upload.png")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        vision_service = VisionService()
        result = await vision_service.analyze_image(tmp_path)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/batch", response_model=list[AnalysisResult])
async def analyze_batch(
    files: list[UploadFile] = File(...),
    current_user: str = Depends(get_current_user),
):
    results = []
    for file in files[:5]:
        # Process each file sequentially for now
        content = await file.read()
        if len(content) > settings.IMAGE_UPLOAD_MAX_SIZE_MB * 1024 * 1024:
            continue

        suffix = os.path.splitext(file.filename or "upload.png")[1]
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            vision_service = VisionService()
            result = await vision_service.analyze_image(tmp_path)
            results.append(result)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return results
