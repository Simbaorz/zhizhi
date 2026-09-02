"""HTTP schemas shared by 致知 management Scene routes."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from zhizhi_admin_api.skills import (
    AdminScopePayload,
    ContentDeleteRequest,
    ContentDirectoryCreateRequest,
    ContentFileWriteRequest,
    ContentMoveRequest,
)
from zhizhi_platform.iam import AdminScopeRef, AdminScopeType

SCENE_SCOPE_FIELDS = {
    "scope_type",
    "scope_tenant_id",
}


class SceneWriteRequest(AdminScopePayload):
    """Create or replace one Scene asset metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    description: str = ""
    status: Literal["enabled", "disabled"] = "enabled"
    source: Literal["admin"] = "admin"
    required_skill_asset_key: str = Field(default="", max_length=64)
    recommended_skill_asset_keys: tuple[str, ...] = ()


class ScenePatchRequest(AdminScopePayload):
    """Patch one Scene asset metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    status: Literal["enabled", "disabled"] | None = None
    source: Literal["admin"] | None = None
    required_skill_asset_key: str | None = Field(default=None, max_length=64)
    recommended_skill_asset_keys: tuple[str, ...] | None = None


class SceneGitCreateRequest(AdminScopePayload):
    """Create one Git-backed Scene asset."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    description: str = ""
    status: Literal["enabled", "disabled"] = "enabled"
    required_skill_asset_key: str = Field(default="", max_length=64)
    recommended_skill_asset_keys: tuple[str, ...] = ()
    git_repository_id: str = Field(min_length=1)
    branch: str = ""
    ref: str = ""
    subdir: str = ""
    auto_sync_enabled: bool = False
    daily_sync_time: str = "03:00"
    timezone: str = "Asia/Shanghai"


class SceneGitPatchRequest(AdminScopePayload):
    """Patch one Git-backed Scene configuration."""

    model_config = ConfigDict(extra="forbid")

    git_repository_id: str | None = None
    branch: str | None = None
    ref: str | None = None
    subdir: str | None = None
    auto_sync_enabled: bool | None = None
    daily_sync_time: str | None = None
    timezone: str | None = None


class SceneContentFileWriteRequest(ContentFileWriteRequest):
    """Write one file under a Scene asset."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str


class SceneContentDirectoryCreateRequest(ContentDirectoryCreateRequest):
    """Create one directory under a Scene asset."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str


class SceneContentMoveRequest(ContentMoveRequest):
    """Move one path under a Scene asset."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str


class SceneContentDeleteRequest(ContentDeleteRequest):
    """Delete one path under a Scene asset."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str


def scene_scope(
    scope_type: AdminScopeType,
    scope_tenant_id: str,
) -> AdminScopeRef:
    return AdminScopePayload(
        scope_type=scope_type,
        scope_tenant_id=scope_tenant_id,
    ).to_scope_ref()
