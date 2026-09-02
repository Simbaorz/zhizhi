"""Typed configuration accepted by the 致知 Worker process."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator

from gewu_core.blocking import BlockingTaskSettings
from gewu_core.config import ApolloBootstrapSettings, SettingsModel
from gewu_core.file_tasks import FileTaskSettings
from gewu_core.logging import LoggingSettings
from gewu_core.secrets import StorageEncryptionSettings
from zhizhi_platform import (
    ChatMediaSettings,
    ZhizhiDatabaseSettings,
    ZhizhiRedisSettings,
)
from zhizhi_platform.git import ZhizhiGitSettings
from zhizhi_platform.workspace import ZhizhiWorkspaceSettings

WORKER_CONFIG_FILE = Path("conf/worker.yml")


class ZhizhiWorkerBootstrapSettings(ApolloBootstrapSettings):
    """Bootstrap values and default YAML path owned by the Worker process."""

    config_file: Path = Field(default=WORKER_CONFIG_FILE, alias="CONFIG_FILE")


class ZhizhiWorkerBlockingIoSettings(BlockingTaskSettings):
    """Blocking execution lanes required by background jobs."""

    filesystem: FileTaskSettings = Field(default_factory=FileTaskSettings)


class ZhizhiCelerySettings(SettingsModel):
    """Celery worker and Scene Git scheduling limits."""

    scene_git_dispatch_interval_seconds: int = Field(default=60, ge=1)
    worker_concurrency: int = Field(default=4, ge=1)
    scene_git_queue: str = Field(
        default="scene_git",
        min_length=1,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    scene_git_soft_time_limit_seconds: int = Field(default=15 * 60, ge=1)
    scene_git_time_limit_seconds: int = Field(default=16 * 60, ge=2)
    publish_timeout_seconds: float = Field(default=5.0, gt=0)

    @model_validator(mode="after")
    def validate_time_limits(self) -> ZhizhiCelerySettings:
        """Require a hard-kill grace period after the soft task limit."""

        if self.scene_git_soft_time_limit_seconds >= self.scene_git_time_limit_seconds:
            raise ValueError(
                "celery.scene_git_soft_time_limit_seconds must be less than "
                "celery.scene_git_time_limit_seconds"
            )
        return self


class ZhizhiWorkerRuntimeSettings(SettingsModel):
    """Worker-owned temporary filesystem settings."""

    temp_dir: str = "temp"


class ZhizhiWorkerSettings(SettingsModel):
    """Complete runtime configuration for one Worker process."""

    blocking_io: ZhizhiWorkerBlockingIoSettings = Field(
        default_factory=ZhizhiWorkerBlockingIoSettings
    )
    celery: ZhizhiCelerySettings = Field(default_factory=ZhizhiCelerySettings)
    db: ZhizhiDatabaseSettings = Field(default_factory=ZhizhiDatabaseSettings)
    storage_encryption: StorageEncryptionSettings = Field(default_factory=StorageEncryptionSettings)
    log: LoggingSettings = Field(default_factory=LoggingSettings)
    media: ChatMediaSettings = Field(default_factory=ChatMediaSettings)
    redis: ZhizhiRedisSettings = Field(default_factory=ZhizhiRedisSettings)
    runtime: ZhizhiWorkerRuntimeSettings = Field(default_factory=ZhizhiWorkerRuntimeSettings)
    scene_git: ZhizhiGitSettings = Field(default_factory=ZhizhiGitSettings)
    workspace: ZhizhiWorkspaceSettings = Field(default_factory=ZhizhiWorkspaceSettings)
