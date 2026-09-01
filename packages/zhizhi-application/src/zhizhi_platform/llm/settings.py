"""Zhizhi Admin outbound model-probe settings."""

from pydantic import Field, model_validator

from gewu_core.config import SettingsModel


class OutboundHttpSettings(SettingsModel):
    """Connection pool and timeout values preserved from Zhizhi configuration."""

    max_connections: int = Field(default=100, ge=1)
    max_keepalive_connections: int = Field(default=20, ge=0)
    keepalive_expiry_seconds: float = Field(default=5.0, gt=0)
    connect_timeout_seconds: float = Field(default=5.0, gt=0)
    pool_timeout_seconds: float = Field(default=5.0, gt=0)

    @model_validator(mode="after")
    def validate_keepalive_capacity(self) -> "OutboundHttpSettings":
        if self.max_keepalive_connections > self.max_connections:
            raise ValueError(
                "outbound_http.max_keepalive_connections must not exceed "
                "outbound_http.max_connections"
            )
        return self
