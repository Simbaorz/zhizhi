"""Local filesystem storage for 致知 Chat media objects."""

from __future__ import annotations

from pathlib import Path

from gewu_core.file_tasks import FileTaskLane, run_file_mutation, run_file_task


class LocalZhizhiChatMediaStore:
    """Store opaque media keys below one configured local root."""

    storage_backend = "local"

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()

    async def save(self, resource_key: str, data: bytes, mime_type: str) -> None:
        del mime_type
        await run_file_mutation(
            self._write,
            resource_key,
            data,
            lane=FileTaskLane.INTERACTIVE,
        )

    async def read(self, resource_key: str) -> bytes:
        return await run_file_task(
            self._read,
            resource_key,
            lane=FileTaskLane.INTERACTIVE,
        )

    async def delete(self, resource_key: str) -> None:
        await run_file_mutation(
            self._delete,
            resource_key,
            lane=FileTaskLane.INTERACTIVE,
        )

    async def close(self) -> None:
        """Release no resources for local filesystem storage."""

    def _path_for(self, resource_key: str) -> Path:
        path = (self._root / resource_key).resolve()
        if self._root not in (path, *path.parents):
            raise ValueError("Invalid media resource key.")
        return path

    def _write(self, resource_key: str, data: bytes) -> None:
        path = self._path_for(resource_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def _read(self, resource_key: str) -> bytes:
        return self._path_for(resource_key).read_bytes()

    def _delete(self, resource_key: str) -> None:
        self._path_for(resource_key).unlink(missing_ok=True)
