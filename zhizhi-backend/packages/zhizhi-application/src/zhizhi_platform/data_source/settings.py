"""Trusted MCP deployment settings; database credentials stay in Admin storage."""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator, model_validator

from gewu_core.config import SettingsModel
from zhizhi_platform.data_source.domain import DataSourceConfig


class _DataMcpAuthSettings(SettingsModel):
    enabled: bool = False
    signing_key: SecretStr = Field(default=SecretStr(""), repr=False)

    @model_validator(mode="after")
    def require_signing_key(self) -> _DataMcpAuthSettings:
        if self.enabled and len(self.signing_key.get_secret_value().encode()) < 32:
            raise ValueError("data_mcp.signing_key must contain at least 32 bytes when enabled")
        return self


class DataMcpClientSettings(_DataMcpAuthSettings):
    """Web/Admin callers; routing comes from each Admin-managed source record."""

    token_ttl_seconds: int = Field(default=60, ge=1)
    max_client_connections: int = Field(default=64, ge=1)


class DataMcpServerSettings(_DataMcpAuthSettings):
    """One query server's identity and business connection-pool budget."""

    server_id: str = Field(default="main", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    public_url: str = "http://127.0.0.1:8002/mcp"
    max_pool_capacity: int = Field(default=96, ge=1, le=4096)
    max_active_pools: int = Field(default=32, ge=1, le=1024)
    idle_pool_seconds: float = Field(default=300, gt=0)
    shutdown_timeout_seconds: float = Field(default=30, gt=0, le=300)

    @field_validator("public_url")
    @classmethod
    def normalize_public_url(cls, value: str) -> str:
        return DataSourceConfig.require_http_endpoint(value)
