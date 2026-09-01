"""Zhizhi Workspace Skill and Scene resource models."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gewu_agent_runtime.skill_contracts import SkillFrontmatterSnapshot
from zhizhi_platform.audit import AuditActor
from zhizhi_platform.iam import AccessScope, AdminScopeRef
from zhizhi_platform.workspace.files import FileVersion


class WorkspaceSkillAsset(BaseModel):
    """DB-backed Zhizhi Skill metadata before Runtime projection."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_id: str = Field(min_length=1)
    scope_type: str = Field(pattern="^tenant$")
    owner_user_id: str | None = None
    asset_key: str = Field(min_length=1)
    name: str = ""
    description: str = ""
    descriptor: SkillFrontmatterSnapshot | None = None
    content_hash: str = ""
    status: str = "enabled"
    source: str = ""
    created_by_actor: AuditActor = Field(default_factory=AuditActor.system)
    updated_by_actor: AuditActor = Field(default_factory=AuditActor.system)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspaceSceneAsset(BaseModel):
    """DB-backed Zhizhi Scene metadata before Runtime projection."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_id: str = Field(min_length=1)
    scope_type: str = Field(pattern="^(tenant|user)$")
    owner_user_id: str | None = None
    asset_key: str = Field(min_length=1)
    name: str = ""
    description: str = ""
    status: str = "enabled"
    required_skill_asset_key: str = ""
    recommended_skill_asset_keys: tuple[str, ...] = ()
    source: str = ""
    created_by_actor: AuditActor = Field(default_factory=AuditActor.system)
    updated_by_actor: AuditActor = Field(default_factory=AuditActor.system)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ManagedFileEntry(BaseModel):
    """Shared Workspace file or directory entry."""

    model_config = ConfigDict(frozen=True)

    entry_type: str = Field(pattern="^(file|directory)$")
    name: str = Field(min_length=1)
    path: str = ""
    size_bytes: int = 0
    version: FileVersion = 0
    modified_at: datetime | None = None


class ManagedTextFile(BaseModel):
    """Managed shared UTF-8 text file."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(min_length=1)
    content: str = ""
    version: FileVersion = 0
    modified_at: datetime | None = None


class WorkspaceSceneAssetRepository(Protocol):
    """Persistence boundary required by Scene Git administration and workers."""

    async def save_scene(self, asset: WorkspaceSceneAsset) -> WorkspaceSceneAsset: ...

    async def scene_name_exists(
        self,
        tenant_id: str,
        *,
        scope_type: str,
        owner_user_id: str | None,
        name: str,
        exclude_asset_key: str = "",
    ) -> bool: ...

    async def get_scene(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        asset_key: str,
    ) -> WorkspaceSceneAsset | None: ...

    async def mark_scene_deleted(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        asset_key: str,
        updated_by_actor: AuditActor,
    ) -> bool: ...


class WorkspaceAssetRepository(WorkspaceSceneAssetRepository, Protocol):
    """Persistence boundary for Zhizhi Workspace Skill and Scene assets."""

    async def save_skill(self, asset: WorkspaceSkillAsset) -> WorkspaceSkillAsset: ...

    async def list_skills_by_scope(
        self,
        tenant_id: str,
        *,
        scope_type: str,
        owner_user_id: str | None = None,
        include_deleted: bool = False,
        limit: int | None = None,
    ) -> Sequence[WorkspaceSkillAsset]: ...

    async def list_skills_for_owner_scope(
        self,
        scope: AccessScope,
        *,
        include_deleted: bool = False,
        limit: int | None = None,
    ) -> Sequence[WorkspaceSkillAsset]: ...

    async def skill_name_exists(
        self,
        tenant_id: str,
        *,
        scope_type: str,
        owner_user_id: str | None,
        name: str,
        exclude_asset_key: str = "",
    ) -> bool: ...

    async def get_skill_by_name(
        self,
        tenant_id: str,
        *,
        scope_type: str,
        owner_user_id: str | None,
        name: str,
        include_deleted: bool = False,
    ) -> WorkspaceSkillAsset | None: ...

    async def get_skill(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        asset_key: str,
    ) -> WorkspaceSkillAsset | None: ...

    async def mark_skill_deleted(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        owner_user_id: str | None,
        asset_key: str,
        updated_by_actor: AuditActor,
    ) -> bool: ...

    async def list_visible_scenes_for_user(
        self,
        tenant_id: str,
        user_id: str,
        *,
        limit: int | None = None,
    ) -> Sequence[WorkspaceSceneAsset]: ...

    async def list_scenes_by_scope(
        self,
        tenant_id: str,
        *,
        scope_type: str,
        owner_user_id: str | None = None,
        include_deleted: bool = False,
        limit: int | None = None,
    ) -> Sequence[WorkspaceSceneAsset]: ...

    async def get_scene_by_name(
        self,
        tenant_id: str,
        *,
        scope_type: str,
        owner_user_id: str | None,
        name: str,
        include_deleted: bool = False,
    ) -> WorkspaceSceneAsset | None: ...


class ManagedWorkspaceRepository(Protocol):
    """Physical persistence boundary for administrator-managed Zhizhi Workspace content."""

    max_file_bytes: int
    max_skill_package_bytes: int
    max_scene_package_bytes: int

    def serialize_mutation(
        self,
        scope: AdminScopeRef,
    ) -> AbstractAsyncContextManager[object]: ...

    async def list_entries(
        self,
        scope: AdminScopeRef,
        path: str = "",
        *,
        include_skills: bool,
    ) -> Sequence[ManagedFileEntry]: ...

    async def read_file(self, scope: AdminScopeRef, path: str) -> ManagedTextFile | None: ...

    async def write_file(
        self,
        scope: AdminScopeRef,
        path: str,
        content: str,
        *,
        expected_version: int | None = None,
    ) -> ManagedTextFile: ...

    async def resolve_download_path_async(
        self,
        scope: AdminScopeRef,
        path: str,
    ) -> Path | None: ...

    async def resolve_managed_path_async(
        self,
        scope: AdminScopeRef,
        path: str,
    ) -> Path | None: ...

    async def resolve_managed_directory_async(
        self,
        scope: AdminScopeRef,
        path: str,
    ) -> Path | None: ...

    async def replace_file_bytes_async(
        self,
        scope: AdminScopeRef,
        path: str,
        content: bytes,
    ) -> ManagedFileEntry: ...

    async def replace_directory_from_path_async(
        self,
        scope: AdminScopeRef,
        path: str,
        source_path: Path,
    ) -> None: ...

    async def create_directory_async(self, scope: AdminScopeRef, path: str) -> None: ...

    async def move_path_async(
        self,
        scope: AdminScopeRef,
        src_path: str,
        dst_path: str,
    ) -> None: ...

    async def delete_path_async(
        self,
        scope: AdminScopeRef,
        path: str,
        *,
        recursive: bool = False,
    ) -> None: ...
