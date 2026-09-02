"""Shared configuration and runtime capabilities for 致知 services."""

from zhizhi_platform.bootstrap import (
    ZhizhiBootstrapSettings,
    resolve_instance_namespace,
    should_auto_create_schema,
    should_enforce_strong_secrets,
)
from zhizhi_platform.data_source.capability import (
    ZhizhiDataSourceCapabilityBuilder,
    ZhizhiDataSourceRuntimeConfig,
    ZhizhiHttpDataSourceCapability,
)
from zhizhi_platform.data_source.resolution import (
    ZhizhiDataSourceBindingRecord,
    ZhizhiDataSourceSourceRecord,
    ZhizhiDataSourceSourceResolver,
)
from zhizhi_platform.database_settings import ZhizhiDatabaseSettings
from zhizhi_platform.llm.resolution import (
    ZhizhiModelBindingRecord,
    ZhizhiModelBindingResolver,
)
from zhizhi_platform.media_settings import ChatMediaOssSettings, ChatMediaSettings
from zhizhi_platform.redis_settings import ZhizhiRedisSettings

__all__ = [
    "ChatMediaOssSettings",
    "ZhizhiBootstrapSettings",
    "resolve_instance_namespace",
    "should_auto_create_schema",
    "should_enforce_strong_secrets",
    "ChatMediaSettings",
    "ZhizhiDataSourceBindingRecord",
    "ZhizhiDataSourceCapabilityBuilder",
    "ZhizhiDataSourceRuntimeConfig",
    "ZhizhiDataSourceSourceRecord",
    "ZhizhiDataSourceSourceResolver",
    "ZhizhiDatabaseSettings",
    "ZhizhiHttpDataSourceCapability",
    "ZhizhiModelBindingRecord",
    "ZhizhiModelBindingResolver",
    "ZhizhiRedisSettings",
]
