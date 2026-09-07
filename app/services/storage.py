import os
import tempfile
import time
from pathlib import Path

from app.core.config import settings
from app.core.logging import ImageAction, log_image_event

MAX_ORPHAN_AGE_SECONDS = 300  # 5 minutes safety net


class StorageService:
    """Privacy-first temporary image storage.

    Images are written to a dedicated temp directory and tracked for
    guaranteed cleanup.  The caller MUST use the returned path inside a
    try/finally that calls `delete_image` – the endpoint layer enforces
    this contract.  A background sweep also catches orphans.
    """

    def __init__(self) -> None:
        self._retention = settings.IMAGE_RETENTION_SECONDS
        self._tmp_dir = Path(tempfile.gettempdir()) / "scg_uploads"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._active: dict[str, float] = {}  # path → creation timestamp

    async def save_temp_image(self, content: bytes, filename: str, user_id: str | None = None) -> str:
        suffix = os.path.splitext(filename or "upload.png")[1] or ".png"
        fd, path = tempfile.mkstemp(suffix=suffix, dir=str(self._tmp_dir))
        try:
            os.write(fd, content)
            os.close(fd)
        except Exception:
            os.close(fd)
            os.unlink(path)
            raise

        self._active[path] = time.time()
        log_image_event(
            ImageAction.UPLOAD,
            filename,
            user_id=user_id,
            file_size=len(content),
            detail=f"path={path}",
        )
        return path

    async def delete_image(self, path: str, user_id: str | None = None) -> bool:
        filename = os.path.basename(path)
        try:
            if os.path.exists(path):
                os.unlink(path)
                log_image_event(
                    ImageAction.DELETE,
                    filename,
                    user_id=user_id,
                    detail=f"path={path}",
                )
            self._active.pop(path, None)
            return True
        except OSError as exc:
            log_image_event(
                ImageAction.DELETE_FAILED,
                filename,
                user_id=user_id,
                detail=f"path={path} error={exc}",
            )
            return False

    async def cleanup_orphans(self) -> int:
        """Remove temp files older than MAX_ORPHAN_AGE_SECONDS."""
        now = time.time()
        removed = 0
        for path in list(self._active.keys()):
            age = now - self._active[path]
            if age > MAX_ORPHAN_AGE_SECONDS and await self.delete_image(path):
                removed += 1
                log_image_event(
                    ImageAction.CLEANUP_ORPHAN,
                    os.path.basename(path),
                    detail=f"age={age:.0f}s",
                )
        # Also sweep the directory for files we lost track of
        for f in self._tmp_dir.iterdir():
            if f.is_file():
                age = now - f.stat().st_mtime
                if age > MAX_ORPHAN_AGE_SECONDS:
                    try:
                        f.unlink()
                        removed += 1
                        log_image_event(
                            ImageAction.CLEANUP_ORPHAN,
                            f.name,
                            detail=f"age={age:.0f}s (orphan sweep)",
                        )
                    except OSError:
                        pass
        return removed

    @property
    def active_count(self) -> int:
        return len(self._active)


storage_service = StorageService()
