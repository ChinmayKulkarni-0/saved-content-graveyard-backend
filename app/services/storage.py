import asyncio
import os
import tempfile
import time
from pathlib import Path

from app.core.config import settings
from app.core.logging import ImageAction, log_image_event


class StorageService:
    """Privacy-first temporary image storage.

    Images are written to a dedicated temp directory and tracked for
    guaranteed cleanup.  The caller MUST use the returned path inside a
    try/finally that calls `delete_image` – the endpoint layer enforces
    this contract.  A background sweep also catches orphans.
    """

    def __init__(self) -> None:
        self._retention_seconds = settings.IMAGE_RETENTION_SECONDS
        self._tmp_dir = Path(settings.IMAGE_TEMP_DIR)
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._active: dict[str, float] = {}  # path → creation timestamp

    async def save_temp_image(self, content: bytes, filename: str, user_id: str | None = None) -> str:
        suffix = os.path.splitext(filename or "upload.png")[1] or ".png"

        def _write() -> str:
            fd, path = tempfile.mkstemp(suffix=suffix, dir=str(self._tmp_dir))
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(content)
            except Exception:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                raise
            return path

        path = await asyncio.to_thread(_write)

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

        def _delete() -> bool:
            if not os.path.exists(path):
                return False
            os.unlink(path)
            return True

        try:
            removed = await asyncio.to_thread(_delete)
            if removed:
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
        """Remove temp files older than IMAGE_RETENTION_SECONDS."""
        retention = self._retention_seconds
        now = time.time()

        def _sweep() -> int:
            removed = 0
            for path in list(self._active.keys()):
                age = now - self._active[path]
                if age > retention:
                    try:
                        if os.path.exists(path):
                            os.unlink(path)
                        removed += 1
                    except OSError:
                        continue
                    finally:
                        self._active.pop(path, None)
            for f in self._tmp_dir.iterdir():
                if f.is_file():
                    try:
                        age = now - f.stat().st_mtime
                        if age > retention:
                            f.unlink()
                            removed += 1
                    except OSError:
                        continue
            return removed

        removed = await asyncio.to_thread(_sweep)
        if removed:
            log_image_event(
                ImageAction.CLEANUP_ORPHAN,
                "cleanup_sweep",
                detail=f"removed={removed} files",
            )
        return removed

    @property
    def active_count(self) -> int:
        return len(self._active)


storage_service = StorageService()