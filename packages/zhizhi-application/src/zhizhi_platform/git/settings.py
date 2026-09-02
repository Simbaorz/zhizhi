"""Typed settings for restricted 致知 Git operations."""

from pydantic import Field

from gewu_core.config import SettingsModel


class ZhizhiGitSettings(SettingsModel):
    """Configuration for subprocess-backed Git operations."""

    command_timeout_seconds: int = Field(default=120, ge=1)
    max_clone_overhead_bytes: int = Field(default=64 * 1024 * 1024, ge=0)
