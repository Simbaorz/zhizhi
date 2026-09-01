"""Outbound adapters used by active Zhizhi processes."""

from zhizhi_platform.adapters.media_factory import (
    build_zhizhi_chat_media_store,
)
from zhizhi_platform.adapters.oss_media import OssZhizhiChatMediaStore

__all__ = [
    "OssZhizhiChatMediaStore",
    "build_zhizhi_chat_media_store",
]
