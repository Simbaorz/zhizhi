"""Typed process configuration for the 致知 Web API."""

from pathlib import Path

from pydantic import Field, model_validator

from gewu_core import StorageEncryptionSettings
from gewu_core.config import ApolloBootstrapSettings, SettingsModel
from gewu_core.http import HttpInfrastructureSettings
from zhizhi_platform import (
    ChatMediaSettings,
    ZhizhiDatabaseSettings,
    ZhizhiRedisSettings,
)
from zhizhi_platform.llm import OutboundHttpSettings
from zhizhi_platform.workspace import ZhizhiWorkspaceSettings

WEB_CONFIG_FILE = Path("conf/web.yml")


class WebApiBootstrapSettings(ApolloBootstrapSettings):
    config_file: Path = Field(default=WEB_CONFIG_FILE, alias="CONFIG_FILE")


class AgentSettings(SettingsModel):
    max_iterations: int = Field(default=50, ge=1)
    max_concurrent_turns_per_process: int = Field(default=32, ge=1)
    queue_capacity: int = Field(default=128, ge=0)
    admission_timeout_seconds: float = Field(default=5.0, gt=0)
    state_cache_ttl_seconds: int = Field(default=24 * 60 * 60, ge=1)
    run_lease_ttl_seconds: int = Field(default=300, ge=3)
    ask_user_timeout_seconds: int = Field(default=300, ge=1)
    pending_ask_cleanup_interval_seconds: int = Field(default=60, ge=1)
    micro_compact_keep_recent_tool_results: int = Field(default=5, ge=0)
    encrypt_tool_results: bool = False
    encrypt_compaction_summaries: bool = False
    image_raw_in_flight_bytes: int = Field(default=128 * 1024 * 1024, ge=1)
    image_encoded_in_flight_bytes: int = Field(default=256 * 1024 * 1024, ge=1)
    image_provider_payload_in_flight_bytes: int = Field(default=256 * 1024 * 1024, ge=1)
    image_admission_timeout_seconds: float = Field(default=2.0, gt=0)


class DataSourceSettings(SettingsModel):
    max_response_bytes: int = Field(default=4 * 1024 * 1024, ge=1)
    max_tool_result_bytes: int = Field(default=512 * 1024, ge=2048)


class WebApiSettings(HttpInfrastructureSettings):
    db: ZhizhiDatabaseSettings = Field(default_factory=ZhizhiDatabaseSettings)
    redis: ZhizhiRedisSettings = Field(default_factory=ZhizhiRedisSettings)
    storage_encryption: StorageEncryptionSettings = Field(default_factory=StorageEncryptionSettings)
    media: ChatMediaSettings = Field(default_factory=ChatMediaSettings)
    workspace: ZhizhiWorkspaceSettings = Field(default_factory=ZhizhiWorkspaceSettings)
    outbound_http: OutboundHttpSettings = Field(default_factory=OutboundHttpSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    data_source: DataSourceSettings = Field(default_factory=DataSourceSettings)

    @model_validator(mode="after")
    def require_workspace_root(self) -> "WebApiSettings":
        if not self.workspace.storage_root.strip():
            raise ValueError("workspace.storage_root is required")
        if not self.media.oss_enable and not self.media.root.strip():
            raise ValueError("media.root is required when media.oss_enable is false")
        return self
