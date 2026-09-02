"""致知 tenant Skill administration service."""

from __future__ import annotations

from pathlib import Path

from gewu_core.archive import PackageContent
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminSessionUser,
    ensure_admin_permission,
)
from zhizhi_platform.iam.ports import AdminOrgReadRepository
from zhizhi_platform.skill.assets import (
    create_managed_skill,
    create_managed_skill_from_package,
    delete_managed_skill,
    get_managed_skill,
    list_managed_skills,
    replace_managed_skill_package,
    update_managed_skill,
)
from zhizhi_platform.skill.files import (
    create_skill_directory,
    delete_skill_path,
    list_skill_entries,
    move_skill_path,
    read_skill_file,
    replace_skill_file_bytes,
    replace_skill_package_bytes,
    resolve_skill_managed_path,
    write_skill_file,
)
from zhizhi_platform.workspace.models import (
    ManagedWorkspaceRepository,
    WorkspaceAssetRepository,
)
from zhizhi_platform.workspace.policy import MAX_UPLOAD_REPLACE_BYTES


class SkillAdminService:
    """Handle 致知 tenant Skill assets and their managed file trees."""

    def __init__(
        self,
        *,
        repository: ManagedWorkspaceRepository,
        asset_repository: WorkspaceAssetRepository,
        org_repository: AdminOrgReadRepository,
    ) -> None:
        self._repository = repository
        self._asset_repository = asset_repository
        self._org_repository = org_repository

    @property
    def max_upload_file_bytes(self) -> int:
        return MAX_UPLOAD_REPLACE_BYTES

    @property
    def max_package_bytes(self) -> int:
        return self._repository.max_skill_package_bytes

    async def list_assets(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "skills.view")
        assets = await list_managed_skills(
            scope,
            session_user,
            self._org_repository,
            self._asset_repository,
        )
        return {
            "skills": [str(asset["asset_key"]) for asset in assets],
            "assets": assets,
        }

    async def get_asset(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        asset_key: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "skills.view")
        return await get_managed_skill(
            scope,
            asset_key,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def create_asset(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        content: str,
        name: str,
        description: str,
        status: str,
        source: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "skills.edit")
        return await create_managed_skill(
            scope,
            content,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
            name=name,
            description=description,
            status=status,
            source=source,
        )

    async def create_asset_from_package(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        name: str,
        content: PackageContent,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "skills.edit")
        return await create_managed_skill_from_package(
            scope,
            content,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
            name=name,
        )

    async def update_asset(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        asset_key: str,
        *,
        content: str,
        name: str,
        description: str,
        status: str,
        source: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "skills.edit")
        return await update_managed_skill(
            scope,
            asset_key,
            content,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
            name=name,
            description=description,
            status=status,
            source=source,
        )

    async def replace_asset_package(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        asset_key: str,
        content: PackageContent,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "skills.edit")
        return await replace_managed_skill_package(
            scope,
            asset_key,
            content,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def delete_asset(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        asset_key: str,
    ) -> None:
        ensure_admin_permission(session_user, "skills.edit")
        await delete_managed_skill(
            scope,
            asset_key,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def list_entries(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        path: str,
    ) -> list[dict[str, object]]:
        ensure_admin_permission(session_user, "skills.view")
        return await list_skill_entries(
            scope,
            path,
            session_user,
            self._org_repository,
            self._repository,
        )

    async def read_file(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        path: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "skills.view")
        return await read_skill_file(
            scope,
            path,
            session_user,
            self._org_repository,
            self._repository,
        )

    async def write_file(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        path: str,
        content: str,
        expected_version: int | None,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "skills.edit")
        return await write_skill_file(
            scope,
            path,
            content,
            expected_version,
            session_user,
            self._org_repository,
            self._repository,
            self._asset_repository,
        )

    async def resolve_download(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        path: str,
    ) -> Path:
        ensure_admin_permission(session_user, "skills.view")
        return await resolve_skill_managed_path(
            scope,
            path,
            session_user,
            self._org_repository,
            self._repository,
        )

    async def replace_file(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        path: str,
        content: bytes,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "skills.edit")
        entry = await replace_skill_file_bytes(
            scope,
            path,
            content,
            session_user,
            self._org_repository,
            self._repository,
            self._asset_repository,
        )
        return entry.model_dump(mode="json")

    async def replace_file_package(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        path: str,
        content: PackageContent,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "skills.edit")
        entry = await replace_skill_package_bytes(
            scope,
            path,
            content,
            session_user,
            self._org_repository,
            self._repository,
        )
        return entry.model_dump(mode="json")

    async def create_directory(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        path: str,
    ) -> None:
        ensure_admin_permission(session_user, "skills.edit")
        await create_skill_directory(
            scope,
            path,
            session_user,
            self._org_repository,
            self._repository,
        )

    async def move_path(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        src_path: str,
        dst_path: str,
    ) -> None:
        ensure_admin_permission(session_user, "skills.edit")
        await move_skill_path(
            scope,
            src_path,
            dst_path,
            session_user,
            self._org_repository,
            self._repository,
        )

    async def delete_path(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        path: str,
        recursive: bool,
    ) -> None:
        ensure_admin_permission(session_user, "skills.edit")
        await delete_skill_path(
            scope,
            path,
            recursive,
            session_user,
            self._org_repository,
            self._repository,
        )
