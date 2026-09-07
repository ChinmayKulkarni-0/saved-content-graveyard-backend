import os
import tempfile

from app.core.config import settings


class StorageService:
    def __init__(self):
        self._cleanup_interval = settings.IMAGE_RETENTION_SECONDS

    async def save_temp_image(self, content: bytes, filename: str) -> str:
        suffix = os.path.splitext(filename)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(content)
        tmp.close()
        return tmp.name

    async def delete_image(self, path: str) -> bool:
        if os.path.exists(path):
            os.unlink(path)
            return True
        return False

    async def cleanup_old_files(self):
        # TODO: Implement periodic cleanup of orphaned temp files
        pass
