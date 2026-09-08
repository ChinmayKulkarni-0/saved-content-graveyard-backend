import logging
import sys
import time
from enum import Enum
from pathlib import Path

from app.core.config import settings


def setup_logging() -> None:
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )

    for name in ("httpcore", "httpx", "openai", "google"):
        logging.getLogger(name).setLevel(logging.WARNING)


class ImageAction(str, Enum):
    UPLOAD = "upload"
    VALIDATE = "validate"
    PROCESS_START = "process_start"
    PROCESS_COMPLETE = "process_complete"
    DELETE = "delete"
    DELETE_FAILED = "delete_failed"
    CLEANUP_ORPHAN = "cleanup_orphan"


logger = logging.getLogger("app")

image_lifecycle_logger = logging.getLogger("image_lifecycle")


def log_image_event(
    action: ImageAction,
    filename: str,
    user_id: str | None = None,
    *,
    detail: str = "",
    file_size: int | None = None,
    duration_ms: float | None = None,
) -> None:
    extra = {
        "action": action.value,
        "image_filename": filename,
        "user_id": user_id,
        "timestamp": time.time(),
    }
    if file_size is not None:
        extra["file_size_bytes"] = file_size
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    if detail:
        extra["detail"] = detail

    msg = f"[{action.value}] filename={filename}"
    if user_id:
        msg += f" user={user_id}"
    if file_size is not None:
        msg += f" size={file_size}B"
    if duration_ms is not None:
        msg += f" duration={duration_ms:.1f}ms"
    if detail:
        msg += f" {detail}"

    image_lifecycle_logger.info(msg, extra=extra)
