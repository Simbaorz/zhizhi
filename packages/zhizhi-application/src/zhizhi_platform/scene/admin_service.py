"""Zhizhi Scene administration service."""

from __future__ import annotations

from pathlib import Path

from gewu_core.archive import PackageContent
from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.git import WorkspaceSceneGitRepository
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminSessionUser,
    ensure_admin_permission,
)
from zhizhi_platform.iam.ports import AdminOrgReadRepository
from zhizhi_platform.scene.assets import (
    create_managed_scene,
    create_managed_scene_from_package,
    delete_managed_scene,
    list_managed_scenes,
    replace_managed_scene_package,
    update_managed_scene,
)
from zhizhi_platform.scene.files import (
    create_managed_scene_directory,
    delete_managed_scene_path,
    list_managed_scene_entries,
    move_managed_scene_path,
    read_managed_scene_file,
    replace_managed_scene_directory_package,
    replace_managed_scene_file_bytes,
    resolve_managed_scene_path,
    write_managed_scene_file,
)
from zhizhi_platform.scene.git import (
    CreateGitSceneCommand,
    SceneGitAdminService,
    UpdateGitSceneConfigCommand,
)
from zhizhi_platform.workspace.models import (
    ManagedWorkspaceRepository,
    WorkspaceAssetRepository,
)
from zhizhi_platform.workspace.policy import MAX_UPLOAD_REPLACE_BYTES


class SceneAdminService:
    """Handle Zhizhi Scene assets and managed file trees."""

    def __init__(
        self,
        *,
        repository: ManagedWorkspaceRepository,
        asset_repository: WorkspaceAssetRepository,
        org_repository: AdminOrgReadRepository,
        scene_git_repository: WorkspaceSceneGitRepository | None = None,
        git_service: SceneGitAdminService | None = None,
    ) -> None:
        self._repository = repository
        self._asset_repository = asset_repository
        self._org_repository = org_repository
        self._scene_git_repository = scene_git_repository
        self._git_service = git_service

    @property
    def max_upload_file_bytes(self) -> int:
        return MAX_UPLOAD_REPLACE_BYTES

    @property
    def max_package_bytes(self) -> int:
        return self._repository.max_scene_package_bytes

    async def list_assets(
        self, session_user: AdminSessionUser, scope: AdminScopeRef
    ) -> list[dict[str, object]]:
        ensure_admin_permission(session_user, "scenes.view")
        configs = (
            await self._git_service.list_configs_by_asset_key(session_user, scope)
            if self._git_service is not None
            else None
        )
        return await list_managed_scenes(
            scope,
            session_user,
            self._org_repository,
            self._asset_repository,
            configs,
        )

    async def create_asset(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        name: str,
        description: str,
        status: str,
        source: str,
        required_skill_asset_key: str,
        recommended_skill_asset_keys: tuple[str, ...],
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.edit")
        return await create_managed_scene(
            scope,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
            name=name,
            description=description,
            status=status,
            source=source,
            required_skill_asset_key=required_skill_asset_key,
            recommended_skill_asset_keys=recommended_skill_asset_keys,
        )

    async def create_asset_from_package(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        name: str,
        content: PackageContent,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.edit")
        return await create_managed_scene_from_package(
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
        scene_asset_key: str,
        *,
        name: str | None,
        description: str | None,
        status: str | None,
        source: str | None,
        required_skill_asset_key: str | None,
        recommended_skill_asset_keys: tuple[str, ...] | None,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.edit")
        return await update_managed_scene(
            scope,
            scene_asset_key,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
            name=name,
            description=description,
            status=status,
            source=source,
            required_skill_asset_key=required_skill_asset_key,
            recommended_skill_asset_keys=recommended_skill_asset_keys,
        )

    async def replace_asset_package(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
        content: PackageContent,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.edit")
        return await replace_managed_scene_package(
            scope,
            scene_asset_key,
            content,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def create_git_asset(self, command: CreateGitSceneCommand) -> dict[str, object]:
        ensure_admin_permission(command.session_user, "scenes.edit")
        return await self._require_git_service().create(command)

    async def get_git_config(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.view")
        return await self._require_git_service().get_config(
            session_user,
            scope,
            scene_asset_key,
        )

    async def update_git_config(
        self,
        command: UpdateGitSceneConfigCommand,
    ) -> dict[str, object]:
        ensure_admin_permission(command.session_user, "scenes.edit")
        return await self._require_git_service().update_config(command)

    async def request_sync(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.edit")
        return await self._require_git_service().request_sync(
            session_user,
            scope,
            scene_asset_key,
        )

    async def get_sync_job(
        self,
        session_user: AdminSessionUser,
        job_id: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.view")
        return await self._require_git_service().get_job(session_user, job_id)

    async def list_sync_jobs(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> list[dict[str, object]]:
        ensure_admin_permission(session_user, "scenes.view")
        return await self._require_git_service().list_jobs(
            session_user,
            scope,
            scene_asset_key,
        )

    def _require_git_service(self) -> SceneGitAdminService:
        if self._git_service is None:
            raise ApplicationError(
                ApplicationErrorKind.UNAVAILABLE,
                "Scene Git service is unavailable.",
            )
        return self._git_service

    async def delete_asset(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> None:
        ensure_admin_permission(session_user, "scenes.edit")
        await delete_managed_scene(
            scope,
            scene_asset_key,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
            self._scene_git_repository,
        )

    async def list_entries(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        scene_id: str,
        path: str,
    ) -> list[dict[str, object]]:
        ensure_admin_permission(session_user, "scenes.view")
        return await list_managed_scene_entries(
            scope,
            scene_id,
            path,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def read_file(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        scene_id: str,
        path: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.view")
        return await read_managed_scene_file(
            scope,
            scene_id,
            path,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def write_file(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        scene_id: str,
        path: str,
        content: str,
        expected_version: int | None,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.edit")
        return await write_managed_scene_file(
            scope,
            scene_id,
            path,
            content,
            expected_version,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def resolve_download(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        scene_id: str,
        path: str,
    ) -> Path:
        ensure_admin_permission(session_user, "scenes.view")
        return await resolve_managed_scene_path(
            scope,
            scene_id,
            path,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def replace_file(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        scene_id: str,
        path: str,
        content: bytes,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.edit")
        return await replace_managed_scene_file_bytes(
            scope,
            scene_id,
            path,
            content,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def replace_directory_package(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        scene_id: str,
        path: str,
        content: PackageContent,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.edit")
        return await replace_managed_scene_directory_package(
            scope,
            scene_id,
            path,
            content,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def create_directory(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        scene_id: str,
        path: str,
    ) -> None:
        ensure_admin_permission(session_user, "scenes.edit")
        await create_managed_scene_directory(
            scope,
            scene_id,
            path,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def move_path(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        scene_id: str,
        src_path: str,
        dst_path: str,
    ) -> None:
        ensure_admin_permission(session_user, "scenes.edit")
        await move_managed_scene_path(
            scope,
            scene_id,
            src_path,
            dst_path,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )

    async def delete_path(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        scene_id: str,
        path: str,
        recursive: bool,
    ) -> None:
        ensure_admin_permission(session_user, "scenes.edit")
        await delete_managed_scene_path(
            scope,
            scene_id,
            path,
            recursive,
            session_user,
            self._org_repository,
            self._asset_repository,
            self._repository,
        )
