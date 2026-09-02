"""致知 Chat media storage composition."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from zhizhi_platform.adapters.filesystem import LocalZhizhiChatMediaStore
from zhizhi_platform.adapters.oss_media import OssZhizhiChatMediaStore
from zhizhi_platform.chat_media import ZhizhiChatMediaStore
from zhizhi_platform.media_settings import ChatMediaSettings


def build_zhizhi_chat_media_store(
    settings: ChatMediaSettings,
    project_home: str | Path,
    *,
    oss_store_factory: Callable[..., ZhizhiChatMediaStore] = OssZhizhiChatMediaStore,
    local_store_factory: Callable[[str | Path], ZhizhiChatMediaStore] = LocalZhizhiChatMediaStore,
) -> ZhizhiChatMediaStore:
    """Build the configured local or S3-compatible 致知 media store."""

    if settings.oss_enable:
        oss = settings.oss
        missing = [
            key
            for key, value in {
                "media.oss.endpoint": oss.endpoint,
                "media.oss.bucket": oss.bucket,
                "media.oss.access_key": oss.access_key,
                "media.oss.secret_key": oss.secret_key,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing OSS media configuration: {', '.join(missing)}")
        return oss_store_factory(
            endpoint=oss.endpoint,
            bucket=oss.bucket,
            access_key=oss.access_key,
            secret_key=oss.secret_key,
            region=oss.region,
            max_connections=oss.max_connections,
            connect_timeout_seconds=oss.connect_timeout_seconds,
            read_timeout_seconds=oss.read_timeout_seconds,
        )
    if not settings.root.strip():
        raise ValueError("media.root must be configured when media.oss_enable is false.")
    root = Path(settings.root).expanduser()
    if not root.is_absolute():
        root = Path(project_home).expanduser().resolve() / root
    return local_store_factory(root)
