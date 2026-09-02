"""Typed 致知 Workspace storage and resource limits."""

from pathlib import Path

from pydantic import Field

from gewu_core.config import SettingsModel


class ZhizhiWorkspaceSettings(SettingsModel):
    """Physical 致知 Workspace settings loaded by a process composition root."""

    storage_root: str = ""
    max_file_bytes: int = Field(default=5 * 1024 * 1024, ge=1)
    max_skill_package_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    max_scene_package_bytes: int = Field(default=500 * 1024 * 1024, ge=1)
    max_listing_entries: int = Field(default=1000, ge=1)


def resolve_workspace_storage_root(
    configured: str,
    project_home: str | Path,
) -> Path:
    """Resolve one configured Workspace root against the deployment project home."""

    value = configured.strip()
    if not value:
        raise ValueError("workspace.storage_root must be configured.")
    root = Path(value).expanduser()
    if not root.is_absolute():
        root = Path(project_home).expanduser().resolve() / root
    return root.resolve()
