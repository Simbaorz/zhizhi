"""Opaque image storage contracts and validation shared by API and Worker processes."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from gewu_core.time import utc_now

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_START_MARKER = b"\xff\xd8\xff"
JPEG_END_MARKER = b"\xff\xd9"
MIME_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png"}
ACCEPTED_IMAGE_MIME_TYPES = tuple(MIME_EXTENSIONS)


class ZhizhiChatMediaStore(Protocol):
    """Store media through opaque keys after application-level authorization."""

    storage_backend: str

    async def save(self, resource_key: str, data: bytes, mime_type: str) -> None: ...

    async def read(self, resource_key: str) -> bytes: ...

    async def delete(self, resource_key: str) -> None: ...

    async def close(self) -> None: ...


def detect_image_upload_mime_type(data: bytes, *, max_image_bytes: int) -> str:
    """Validate bytes by signature instead of trusting the multipart content type."""

    if not data:
        raise ValueError("Image content is empty.")
    if len(data) > max_image_bytes:
        raise ValueError("Image exceeds max size.")
    if data.startswith(PNG_SIGNATURE):
        return "image/png"
    if data.startswith(JPEG_START_MARKER) and data.endswith(JPEG_END_MARKER):
        return "image/jpeg"
    raise ValueError("Only valid JPG and PNG image files are supported.")


def image_extension_for_mime(mime_type: str) -> str:
    extension = MIME_EXTENSIONS.get(mime_type)
    if extension is None:
        raise ValueError("Only JPG and PNG images are supported.")
    return extension


def build_chat_media_resource_key(
    attachment_id: str,
    mime_type: str,
    *,
    created_at: datetime | None = None,
    prefix: str = "chat_attachments",
) -> str:
    timestamp = created_at or utc_now()
    clean_prefix = prefix.strip().strip("/")
    date_key = f"{timestamp:%Y}/{timestamp:%m}/{attachment_id}{image_extension_for_mime(mime_type)}"
    return f"{clean_prefix}/{date_key}" if clean_prefix else date_key
