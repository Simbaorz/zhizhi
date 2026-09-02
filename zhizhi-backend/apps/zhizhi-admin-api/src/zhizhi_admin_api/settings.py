"""Complete typed configuration accepted by the 致知 Admin API process."""

from pathlib import Path

from pydantic import Field, field_validator

from gewu_core import StorageEncryptionSettings
from gewu_core.config import SettingsModel
from gewu_core.http import (
    HttpInfrastructureSettings,
    HttpIngressSettings,
    PasswordTransportSettings,
)
from zhizhi_platform import (
    ZhizhiBootstrapSettings,
    ZhizhiDatabaseSettings,
    ZhizhiRedisSettings,
)
from zhizhi_platform.git import ZhizhiGitSettings
from zhizhi_platform.iam import IamLimitsSettings, JwtSettings, LoginThrottleSettings
from zhizhi_platform.llm import OutboundHttpSettings
from zhizhi_platform.workspace import ZhizhiWorkspaceSettings

ADMIN_CONFIG_FILE = Path("conf/admin.yml")


class AdminApiBootstrapSettings(ZhizhiBootstrapSettings):
    """Bootstrap values and default YAML path owned by the Admin API process."""

    config_file: Path = Field(default=ADMIN_CONFIG_FILE, alias="CONFIG_FILE")
    admin_session_cookie_secure: bool = Field(
        default=False,
        alias="ADMIN_SESSION_COOKIE_SECURE",
    )
    admin_require_password_transport: bool = Field(
        default=True,
        alias="ADMIN_REQUIRE_PASSWORD_TRANSPORT",
    )
    admin_bootstrap_token: str = Field(
        default="",
        alias="ADMIN_BOOTSTRAP_TOKEN",
        exclude=True,
        repr=False,
    )

    @field_validator("admin_bootstrap_token")
    @classmethod
    def validate_admin_bootstrap_token(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and len(normalized.encode("utf-8")) < 32:
            raise ValueError("ADMIN_BOOTSTRAP_TOKEN must contain at least 32 bytes")
        return normalized


class AdminHttpIngressSettings(HttpIngressSettings):
    """Request size limits owned by 致知's management API routes."""

    admin_json_max_bytes: int = Field(default=1024 * 1024, ge=1024)


class AdminCelerySettings(SettingsModel):
    """Celery publication settings needed by the Admin process."""

    scene_git_queue: str = Field(
        default="scene_git",
        min_length=1,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    publish_timeout_seconds: float = Field(default=5.0, gt=0)


class AdminApiSettings(HttpInfrastructureSettings):
    """Admin process settings loaded from one Bootstrap-selected YAML file."""

    db: ZhizhiDatabaseSettings = Field(default_factory=ZhizhiDatabaseSettings)
    password_transport: PasswordTransportSettings = Field(default_factory=PasswordTransportSettings)
    http_ingress: AdminHttpIngressSettings = Field(default_factory=AdminHttpIngressSettings)
    jwt: JwtSettings = Field(default_factory=JwtSettings)
    storage_encryption: StorageEncryptionSettings = Field(default_factory=StorageEncryptionSettings)
    login_throttle: LoginThrottleSettings = Field(default_factory=LoginThrottleSettings)
    celery: AdminCelerySettings = Field(default_factory=AdminCelerySettings)
    iam: IamLimitsSettings = Field(default_factory=IamLimitsSettings)
    scene_git: ZhizhiGitSettings = Field(default_factory=ZhizhiGitSettings)
    outbound_http: OutboundHttpSettings = Field(default_factory=OutboundHttpSettings)
    redis: ZhizhiRedisSettings = Field(default_factory=ZhizhiRedisSettings)
    workspace: ZhizhiWorkspaceSettings = Field(default_factory=ZhizhiWorkspaceSettings)
