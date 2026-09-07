import logging
import time
from enum import Enum


class ImageAction(str, Enum):
    UPLOAD = "upload"
    VALIDATE = "validate"
    PROCESS_START = "process_start"
    PROCESS_COMPLETE = "process_complete"
    DELETE = "delete"
    DELETE_FAILED = "delete_failed"
    CLEANUP_ORPHAN = "cleanup_orphan"


logger = logging.getLogger("image_lifecycle")


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
        "filename": filename,
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

    logger.info(msg, extra=extra)
