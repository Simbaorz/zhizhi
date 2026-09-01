"""Shared Zhizhi Chat media configuration."""

from pydantic import Field

from gewu_core.config import SettingsModel


class ChatMediaOssSettings(SettingsModel):
    """S3/MinIO-compatible media storage settings."""

    endpoint: str = ""
    bucket: str = ""
    access_key: str = Field(default="", exclude=True, repr=False)
    secret_key: str = Field(default="", exclude=True, repr=False)
    region: str = ""
    prefix: str = "chat_attachments"
    max_connections: int = Field(default=10, ge=1)
    connect_timeout_seconds: float = Field(default=5.0, gt=0)
    read_timeout_seconds: float = Field(default=30.0, gt=0)


class ChatMediaSettings(SettingsModel):
    """Zhizhi Chat media storage, image limits, and cleanup policy."""

    root: str = ""
    oss_enable: bool = False
    max_image_bytes: int = Field(default=5 * 1024 * 1024, ge=1)
    max_images_per_message: int = Field(default=4, ge=1)
    pending_attachment_ttl_hours: int = Field(default=24, ge=1)
    cleanup_interval_seconds: int = Field(default=3600, ge=60)
    oss: ChatMediaOssSettings = Field(default_factory=ChatMediaOssSettings)
