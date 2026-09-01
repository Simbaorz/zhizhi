"""Zhizhi shared Skill and Scene management services."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import TypedDict
from uuid import uuid4

from zhizhi.assets import (
    MysqlSharedAssetRepository,
    SharedAsset,
    SharedAssetKind,
    SharedScopeType,
)

from gewu_core.archive import PackageContent
from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.file_tasks import run_file_mutation, run_file_task
from gewu_core.file_transactions import (
    remove_directory_created_on_error,
    restore_directory_on_error,
)
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
    ensure_admin_permission,
)
from zhizhi_platform.iam.ports import AdminOrgReadRepository
from zhizhi_platform.scene.git import (
    CreateGitSceneCommand,
    SceneGitAdminService,
    UpdateGitSceneConfigCommand,
    scene_git_config_to_public_dict,
)
from zhizhi_platform.workspace.errors import ConflictError
from zhizhi_platform.workspace.manifest_sync import SkillManifestSynchronizer
from zhizhi_platform.workspace.models import ManagedWorkspaceRepository
from zhizhi_platform.workspace.packages import (
    package_content_size_async,
    package_skill_manifest,
    replace_managed_directory_with_package,
    validate_package_content,
    validated_asset_skill_content,
)
from zhizhi_platform.workspace.policy import (
    MAX_UPLOAD_REPLACE_BYTES,
    hydrate_content_scope,
    managed_asset_mutation_path,
    normalize_skill_path,
    require_manage_scope,
    require_scene_asset_child_path,
    require_skill_asset_child_path,
    validate_scene_name,
    validate_skill_name,
)


class ExactScope(TypedDict):
    tenant_id: str
    scope_type: SharedScopeType


class ZhizhiAssetAdminService:
    """Manage one Skill or Scene kind in a tenant Workspace root."""

    def __init__(
        self,
        *,
        kind: SharedAssetKind,
        repository: ManagedWorkspaceRepository,
        assets: MysqlSharedAssetRepository,
        org_repository: AdminOrgReadRepository,
        scene_git_service: SceneGitAdminService | None = None,
    ) -> None:
        self.kind = kind
        self._repository = repository
        self._assets = assets
        self._org_repository = org_repository
        self._scene_git_service = scene_git_service

    @property
    def max_upload_file_bytes(self) -> int:
        return MAX_UPLOAD_REPLACE_BYTES

    @property
    def max_package_bytes(self) -> int:
        return (
            self._repository.max_skill_package_bytes
            if self.kind == "skill"
            else self._repository.max_scene_package_bytes
        )

    async def list_assets(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
    ) -> dict[str, object] | list[dict[str, object]]:
        hydrated = await self._authorize(session_user, scope, edit=False)
        exact = _exact_scope(hydrated)
        assets = await self._assets.list_exact(kind=self.kind, **exact)
        git_configs = (
            await self._scene_git_service.list_configs_by_asset_key(session_user, scope)
            if (
                self.kind == "scene"
                and self._scene_git_service is not None
                and scope.scope_type is AdminScopeType.TENANT
            )
            else {}
        )
        rows = [
            self._public(
                asset,
                git=(
                    scene_git_config_to_public_dict(git_configs[asset.asset_key])
                    if asset.asset_key in git_configs
                    else None
                ),
            )
            for asset in assets
        ]
        if self.kind == "skill":
            return {"skills": [asset.asset_key for asset in assets], "assets": rows}
        return rows

    async def create_git_asset(self, command: CreateGitSceneCommand) -> dict[str, object]:
        return await self._require_scene_git_service().create(command)

    async def get_git_config(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> dict[str, object]:
        return await self._require_scene_git_service().get_config(
            session_user,
            scope,
            scene_asset_key,
        )

    async def update_git_config(
        self,
        command: UpdateGitSceneConfigCommand,
    ) -> dict[str, object]:
        return await self._require_scene_git_service().update_config(command)

    async def request_sync(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> dict[str, object]:
        return await self._require_scene_git_service().request_sync(
            session_user,
            scope,
            scene_asset_key,
        )

    async def get_sync_job(
        self,
        session_user: AdminSessionUser,
        job_id: str,
    ) -> dict[str, object]:
        return await self._require_scene_git_service().get_job(session_user, job_id)

    async def list_sync_jobs(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> list[dict[str, object]]:
        return await self._require_scene_git_service().list_jobs(
            session_user,
            scope,
            scene_asset_key,
        )

    def _require_scene_git_service(self) -> SceneGitAdminService:
        if self.kind != "scene" or self._scene_git_service is None:
            raise _scene_git_unavailable()
        return self._scene_git_service

    async def get_asset(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        asset_key: str,
    ) -> dict[str, object]:
        hydrated, asset = await self._asset_context(session_user, scope, asset_key, edit=False)
        file = await self._repository.read_file(hydrated, self._main_file(asset))
        if file is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Asset content does not exist.")
        return {
            **self._public(asset),
            "skill_name": asset.name,
            "layout": "directory",
            "main_file_path": file.path,
            "content": file.content,
            "version": str(file.version),
        }

    async def create_asset(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        name: str,
        description: str,
        status: str,
        source: str,
        content: str = "",
        required_skill_asset_key: str = "",
        recommended_skill_asset_keys: tuple[str, ...] = (),
    ) -> dict[str, object]:
        hydrated = await self._authorize(session_user, scope, edit=True)
        asset_name = self._validate_name(name)
        await self._require_name_available(hydrated, asset_name)
        root = self._root(asset_name)
        if await self._repository.resolve_managed_path_async(hydrated, root) is not None:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "Asset directory already exists.")
        await self._repository.create_directory_async(hydrated, root)
        descriptor: dict[str, object] = {}
        content_hash = ""
        if self.kind == "skill":
            content, manifest = validated_asset_skill_content(
                content,
                name=asset_name,
                description=description,
            )
            descriptor = manifest.frontmatter.model_dump(mode="json")
            content_hash = manifest.content_hash
            await self._repository.write_file(hydrated, self._main_file_name(asset_name), content)
        asset = SharedAsset(
            asset_key=f"{self.kind}_{uuid4().hex}",
            kind=self.kind,
            name=asset_name,
            description=description,
            status=status,
            content_hash=content_hash,
            descriptor=descriptor,
            required_skill_asset_key=required_skill_asset_key,
            recommended_skill_asset_keys=recommended_skill_asset_keys,
            source=source,
            created_by_admin_user_id=session_user.user.id,
            updated_by_admin_user_id=session_user.user.id,
            **_exact_scope(hydrated),
        )
        try:
            saved = await self._assets.save(asset)
        except Exception:
            await self._repository.delete_path_async(hydrated, root, recursive=True)
            raise
        return await self._detail(hydrated, saved)

    async def update_asset(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        asset_key: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        source: str | None = None,
        content: str | None = None,
        required_skill_asset_key: str | None = None,
        recommended_skill_asset_keys: tuple[str, ...] | None = None,
    ) -> dict[str, object]:
        hydrated, current = await self._asset_context(session_user, scope, asset_key, edit=True)
        next_name = self._validate_name(name if name is not None else current.name)
        if next_name != current.name:
            await self._require_name_available(hydrated, next_name)
            await self._repository.move_path_async(
                hydrated,
                self._root(current.name),
                self._root(next_name),
            )
        next_description = description if description is not None else current.description
        descriptor = dict(current.descriptor)
        content_hash = current.content_hash
        if self.kind == "skill" and content is not None:
            normalized, manifest = validated_asset_skill_content(
                content,
                name=next_name,
                description=next_description,
            )
            file = await self._repository.write_file(  # noqa
                hydrated,
                self._main_file_name(next_name),
                normalized,
            )
            del file
            descriptor = manifest.frontmatter.model_dump(mode="json")
            content_hash = manifest.content_hash
        saved = await self._assets.save(
            current.model_copy(
                update={
                    "name": next_name,
                    "description": next_description,
                    "status": status if status is not None else current.status,
                    "source": (
                        "git"
                        if self.kind == "scene" and current.source == "git"
                        else source if source is not None else current.source
                    ),
                    "descriptor": descriptor,
                    "content_hash": content_hash,
                    "required_skill_asset_key": (
                        required_skill_asset_key
                        if required_skill_asset_key is not None
                        else current.required_skill_asset_key
                    ),
                    "recommended_skill_asset_keys": (
                        recommended_skill_asset_keys
                        if recommended_skill_asset_keys is not None
                        else current.recommended_skill_asset_keys
                    ),
                    "updated_by_admin_user_id": session_user.user.id,
                }
            )
        )
        return await self._detail(hydrated, saved)

    async def delete_asset(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        asset_key: str,
    ) -> None:
        hydrated, current = await self._asset_context(session_user, scope, asset_key, edit=True)
        await self._repository.delete_path_async(
            hydrated,
            self._root(current.name),
            recursive=True,
        )
        if current.source == "git":
            await self._require_scene_git_service().delete_config(
                session_user,
                scope,
                asset_key,
            )
        await self._assets.save(
            current.model_copy(
                update={
                    "status": "deleted",
                    "updated_by_admin_user_id": session_user.user.id,
                }
            )
        )

    async def list_entries(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        path: str = "",
        *,
        scene_id: str = "",
    ) -> list[dict[str, object]]:
        hydrated = await self._authorize(session_user, scope, edit=False)
        target, root = await self._file_target(hydrated, scene_id, path)
        entries = await self._repository.list_entries(hydrated, target, include_skills=True)
        return [self._entry(root, entry.model_dump(mode="json")) for entry in entries]

    async def read_file(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        path: str = "",
        *,
        scene_id: str = "",
    ) -> dict[str, object]:
        hydrated = await self._authorize(session_user, scope, edit=False)
        target, root = await self._file_target(hydrated, scene_id, path)
        file = await self._repository.read_file(hydrated, target)
        if file is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Asset file does not exist.")
        return self._entry(root, file.model_dump(mode="json"))

    async def write_file(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        path: str,
        content: str,
        expected_version: int | None,
        scene_id: str = "",
    ) -> dict[str, object]:
        hydrated = await self._authorize(session_user, scope, edit=True)
        self._require_mutable_file_path(path)
        target, root = await self._file_target(hydrated, scene_id, path)
        try:
            file = await self._repository.write_file(
                hydrated,
                target,
                content,
                expected_version=expected_version,
            )
        except ConflictError as exc:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, str(exc)) from exc
        if self.kind == "skill" and target.endswith("/SKILL.md"):
            await self._sync_skill_manifest(hydrated, target, content, session_user.user.id)
        return self._entry(root, file.model_dump(mode="json"))

    async def resolve_download(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        path: str = "",
        *,
        scene_id: str = "",
    ) -> Path:
        hydrated = await self._authorize(session_user, scope, edit=False)
        target, _ = await self._file_target(hydrated, scene_id, path)
        resolved = await self._repository.resolve_managed_path_async(hydrated, target)
        if resolved is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Asset path does not exist.")
        return resolved

    async def replace_file(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        path: str,
        content: bytes,
        scene_id: str = "",
    ) -> dict[str, object]:
        if len(content) > self.max_upload_file_bytes:
            raise ApplicationError(
                ApplicationErrorKind.PAYLOAD_TOO_LARGE, "Uploaded file is too large."
            )
        hydrated = await self._authorize(session_user, scope, edit=True)
        self._require_mutable_file_path(path)
        target, root = await self._file_target(hydrated, scene_id, path)
        entry = await self._repository.replace_file_bytes_async(hydrated, target, content)
        if self.kind == "skill" and target.endswith("/SKILL.md"):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "SKILL.md must be UTF-8 text.",
                ) from exc
            await self._sync_skill_manifest(hydrated, target, text, session_user.user.id)
        return self._entry(root, entry.model_dump(mode="json"))

    async def create_directory(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        path: str,
        *,
        scene_id: str = "",
    ) -> None:
        hydrated = await self._authorize(session_user, scope, edit=True)
        self._require_mutable_file_path(path)
        target, _ = await self._file_target(hydrated, scene_id, path)
        await self._repository.create_directory_async(hydrated, target)

    async def move_path(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        src_path: str,
        dst_path: str,
        scene_id: str = "",
    ) -> None:
        hydrated = await self._authorize(session_user, scope, edit=True)
        self._require_mutable_file_path(src_path)
        self._require_mutable_file_path(dst_path)
        source, _ = await self._file_target(hydrated, scene_id, src_path)
        target, _ = await self._file_target(hydrated, scene_id, dst_path)
        await self._repository.move_path_async(hydrated, source, target)

    async def delete_path(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        path: str,
        recursive: bool,
        scene_id: str = "",
    ) -> None:
        hydrated = await self._authorize(session_user, scope, edit=True)
        self._require_mutable_file_path(path)
        target, _ = await self._file_target(hydrated, scene_id, path)
        await self._repository.delete_path_async(hydrated, target, recursive=recursive)

    async def create_asset_from_package(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        name: str,
        content: PackageContent,
    ) -> dict[str, object]:
        hydrated = await self._authorize(session_user, scope, edit=True)
        asset_name = self._validate_name(name)
        await self._require_name_available(hydrated, asset_name)
        manifest = None
        if await package_content_size_async(content) > self.max_package_bytes:
            raise ApplicationError(
                ApplicationErrorKind.PAYLOAD_TOO_LARGE, "Asset package is too large."
            )
        if self.kind == "skill":
            manifest = await run_file_task(
                package_skill_manifest,
                content,
                self.max_package_bytes,
                asset_name,
            )
        else:
            await run_file_task(
                validate_package_content,
                content,
                self.max_package_bytes,
                "Scene",
            )
        root = self._root(asset_name)
        if await self._repository.resolve_managed_path_async(hydrated, root) is not None:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "Asset directory already exists.")
        target = await managed_asset_mutation_path(self._repository, hydrated, root)
        async with remove_directory_created_on_error(
            target,
            mutation_lock=self._repository.serialize_mutation(hydrated),
        ):
            await self._repository.create_directory_async(hydrated, root)
            entry = await self._replace_directory_package(
                hydrated,
                root,
                content,
                require_skill_main_file=self.kind == "skill",
            )
            asset = SharedAsset(
                asset_key=f"{self.kind}_{uuid4().hex}",
                kind=self.kind,
                name=asset_name,
                description=manifest.descriptor.description if manifest is not None else "",
                status="enabled",
                content_hash=manifest.content_hash if manifest is not None else "",
                descriptor=(
                    manifest.frontmatter.model_dump(mode="json") if manifest is not None else {}
                ),
                source="upload",
                created_by_admin_user_id=session_user.user.id,
                updated_by_admin_user_id=session_user.user.id,
                **_exact_scope(hydrated),
            )
            saved = await self._assets.save(asset)
        detail = await self._detail(hydrated, saved)
        return {**detail, "entry": entry} if self.kind == "scene" else detail

    async def replace_asset_package(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        asset_key: str,
        content: PackageContent,
    ) -> dict[str, object]:
        hydrated, asset = await self._asset_context(session_user, scope, asset_key, edit=True)
        if await package_content_size_async(content) > self.max_package_bytes:
            raise ApplicationError(
                ApplicationErrorKind.PAYLOAD_TOO_LARGE, "Asset package is too large."
            )
        manifest = None
        next_name = asset.name
        if self.kind == "skill":
            manifest = await run_file_task(
                package_skill_manifest,
                content,
                self.max_package_bytes,
            )
            next_name = self._validate_name(manifest.descriptor.name)
            if next_name != asset.name:
                await self._require_name_available(hydrated, next_name)
        current_root = self._root(asset.name)
        next_root = self._root(next_name)
        current_target = await managed_asset_mutation_path(self._repository, hydrated, current_root)
        next_target = await managed_asset_mutation_path(self._repository, hydrated, next_root)
        if next_name != asset.name and await run_file_task(next_target.exists):
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "Skill directory already exists.")
        async with restore_directory_on_error(
            current_target,
            cleanup_paths=(next_target,),
            mutation_lock=self._repository.serialize_mutation(hydrated),
        ):
            await self._replace_directory_package(
                hydrated,
                current_root,
                content,
                require_skill_main_file=self.kind == "skill",
            )
            if next_name != asset.name:
                await self._repository.move_path_async(hydrated, current_root, next_root)
            saved = await self._assets.save(
                asset.model_copy(
                    update={
                        "name": next_name,
                        "description": (
                            manifest.descriptor.description
                            if manifest is not None
                            else asset.description
                        ),
                        "content_hash": (
                            manifest.content_hash if manifest is not None else asset.content_hash
                        ),
                        "descriptor": (
                            manifest.frontmatter.model_dump(mode="json")
                            if manifest is not None
                            else asset.descriptor
                        ),
                        "source": "upload",
                        "updated_by_admin_user_id": session_user.user.id,
                    }
                )
            )
        return await self._detail(hydrated, saved)

    async def replace_file_package(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        path: str,
        content: PackageContent,
    ) -> dict[str, object]:
        hydrated = await self._authorize(session_user, scope, edit=True)
        self._require_mutable_file_path(path)
        target = normalize_skill_path(path, allow_root=False)
        return await self._replace_directory_package(hydrated, target, content)

    async def replace_directory_package(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        scene_id: str,
        path: str,
        content: PackageContent,
    ) -> dict[str, object]:
        hydrated = await self._authorize(session_user, scope, edit=True)
        self._require_mutable_file_path(path)
        target, root = await self._file_target(hydrated, scene_id, path)
        entry = await self._replace_directory_package(hydrated, target, content)
        return self._entry(root, entry)

    async def _replace_directory_package(
        self,
        scope: AdminScopeRef,
        path: str,
        content: PackageContent,
        *,
        require_skill_main_file: bool = False,
    ) -> dict[str, object]:
        if await package_content_size_async(content) > self.max_package_bytes:
            raise ApplicationError(
                ApplicationErrorKind.PAYLOAD_TOO_LARGE, "Asset package is too large."
            )
        target = await self._repository.resolve_managed_directory_async(scope, path)
        if target is None:
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND, "Asset directory does not exist."
            )
        entry = await run_file_mutation(
            replace_managed_directory_with_package,
            target,
            path,
            content,
            self.max_package_bytes,
            require_skill_main_file=require_skill_main_file,
            package_kind=self.kind.title(),
        )
        return entry.model_dump(mode="json")

    async def _authorize(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        *,
        edit: bool,
    ) -> AdminScopeRef:
        if scope.scope_type is not AdminScopeType.TENANT:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Skill and Scene assets can only be managed at tenant scope.",
            )
        permission = f"{self.kind}s.{'edit' if edit else 'view'}"
        ensure_admin_permission(session_user, permission)
        hydrated = await hydrate_content_scope(scope, self._org_repository)
        require_manage_scope(session_user, hydrated, permission)
        return hydrated

    async def _asset_context(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        asset_key: str,
        *,
        edit: bool,
    ) -> tuple[AdminScopeRef, SharedAsset]:
        hydrated = await self._authorize(session_user, scope, edit=edit)
        return hydrated, await self._require_asset(hydrated, asset_key)

    async def _require_asset(self, scope: AdminScopeRef, asset_key: str) -> SharedAsset:
        asset = await self._assets.get_exact(
            kind=self.kind, asset_key=asset_key, **_exact_scope(scope)
        )
        if asset is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Asset does not exist.")
        return asset

    async def _require_name_available(self, scope: AdminScopeRef, name: str) -> None:
        assets = await self._assets.list_exact(kind=self.kind, **_exact_scope(scope))
        if any(asset.name.strip().upper() == name.strip().upper() for asset in assets):
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT,
                f"{self.kind.title()} name already exists.",
            )

    async def _detail(self, scope: AdminScopeRef, asset: SharedAsset) -> dict[str, object]:
        if self.kind != "skill":
            return self._public(asset)
        file = await self._repository.read_file(scope, self._main_file(asset))
        if file is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Skill content does not exist.")
        return {
            **self._public(asset),
            "skill_name": asset.name,
            "layout": "directory",
            "main_file_path": file.path,
            "content": file.content,
            "version": str(file.version),
        }

    async def _file_target(
        self,
        scope: AdminScopeRef,
        asset_key: str,
        path: str,
    ) -> tuple[str, str]:
        if self.kind == "skill":
            target = normalize_skill_path(path, allow_root=True)
            return target, ""
        asset = await self._require_asset(scope, asset_key)
        root = self._root(asset.name)
        child = _safe_relative(path, allow_empty=True)
        return (root if not child else f"{root}/{child}"), root

    async def _sync_skill_manifest(
        self,
        scope: AdminScopeRef,
        path: str,
        content: str,
        admin_user_id: str,
    ) -> None:
        parts = PurePosixPath(path).parts
        if len(parts) != 3 or parts[0] != ".skills" or parts[2] != "SKILL.md":
            return
        manifest = SkillManifestSynchronizer.prepare(content, expected_name=parts[1])
        assets = await self._assets.list_exact(kind="skill", **_exact_scope(scope))
        current = next((asset for asset in assets if asset.name == parts[1]), None)
        if current is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Skill metadata does not exist.")
        await self._assets.save(
            current.model_copy(
                update={
                    "description": manifest.descriptor.description,
                    "descriptor": manifest.frontmatter.model_dump(mode="json"),
                    "content_hash": manifest.content_hash,
                    "updated_by_admin_user_id": admin_user_id,
                }
            )
        )

    def _validate_name(self, name: str) -> str:
        return validate_skill_name(name) if self.kind == "skill" else validate_scene_name(name)

    def _require_mutable_file_path(self, path: str) -> None:
        if self.kind == "skill":
            require_skill_asset_child_path(path)
        else:
            require_scene_asset_child_path(path)

    def _root(self, name: str) -> str:
        return f".{self.kind}s/{name}"

    def _main_file_name(self, name: str) -> str:  # noqa
        return f".skills/{name}/SKILL.md"

    def _main_file(self, asset: SharedAsset) -> str:
        return self._main_file_name(asset.name) if self.kind == "skill" else self._root(asset.name)

    def _public(
        self,
        asset: SharedAsset,
        *,
        git: dict[str, object] | None = None,
    ) -> dict[str, object]:
        common: dict[str, object] = {
            "id": asset.asset_key,
            "asset_key": asset.asset_key,
            "name": asset.name,
            "description": asset.description,
            "path": self._root(asset.name),
            "status": asset.status,
            "source": asset.source,
            "scope_type": asset.scope_type,
            "owner_user_id": None,
            "created_at": asset.created_at,
            "updated_at": asset.updated_at,
        }
        if self.kind == "scene":
            common.update(
                {
                    "mode": "auto",
                    "readonly": asset.source == "git",
                    "required_skill_asset_key": asset.required_skill_asset_key,
                    "recommended_skill_asset_keys": list(asset.recommended_skill_asset_keys),
                    "git": git,
                }
            )
        return common

    @staticmethod
    def _entry(root: str, payload: dict[str, object]) -> dict[str, object]:
        if root and isinstance(payload.get("path"), str):
            value = str(payload["path"])  # noqa
            payload = {**payload, "path": value.removeprefix(root).lstrip("/")}
        return payload


def _exact_scope(scope: AdminScopeRef) -> ExactScope:
    if scope.scope_type is AdminScopeType.TENANT:
        return {
            "tenant_id": scope.scope_tenant_id,
            "scope_type": "tenant",
        }
    raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "Unsupported asset scope.")


def _safe_relative(path: str, *, allow_empty: bool) -> str:
    normalized = path.replace("\\", "/").strip().strip("/")
    if not normalized and allow_empty:
        return ""
    parsed = PurePosixPath(normalized)
    if (
        not normalized
        or parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "Invalid asset path.")
    return parsed.as_posix()


def _scene_git_unavailable() -> ApplicationError:
    return ApplicationError(
        ApplicationErrorKind.UNAVAILABLE,
        "Scene Git is not configured for Zhizhi shared assets.",
    )
