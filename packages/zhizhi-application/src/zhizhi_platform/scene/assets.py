"""Zhizhi tenant Scene metadata and package lifecycle use cases."""

from __future__ import annotations

from gewu_core.archive import PackageContent
from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.file_tasks import run_file_mutation, run_file_task
from gewu_core.file_transactions import (
    quarantine_path_until_success,
    remove_directory_created_on_error,
    restore_directory_on_error,
)
from zhizhi_platform.audit import AuditActor
from zhizhi_platform.git import WorkspaceSceneGitConfig, WorkspaceSceneGitRepository
from zhizhi_platform.iam import AdminScopeRef, AdminSessionUser
from zhizhi_platform.iam.ports import AdminOrgReadRepository
from zhizhi_platform.workspace.models import (
    ManagedWorkspaceRepository,
    WorkspaceAssetRepository,
    WorkspaceSceneAsset,
)
from zhizhi_platform.workspace.packages import (
    package_content_size_async,
    replace_managed_directory_with_package,
    validate_package_content,
)
from zhizhi_platform.workspace.policy import (
    DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
    ensure_scene_content_writable,
    ensure_scene_name_available,
    managed_asset_mutation_path,
    managed_scene_context,
    new_scene_asset_key,
    require_asset_directory_absent,
    scene_content_path,
    scene_to_dict,
    tenant_storage_and_asset_scope,
    validate_scene_name,
)


async def list_managed_scenes(
    scope: AdminScopeRef,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    scene_git_configs: dict[str, WorkspaceSceneGitConfig] | None = None,
) -> list[dict[str, object]]:
    _, asset_scope = await tenant_storage_and_asset_scope(
        scope,
        session_user,
        org_repository,
        permission_code="scenes.view",
    )
    scenes = await asset_repository.list_scenes_by_scope(
        asset_scope.tenant_id,
        scope_type=asset_scope.scope_type,
        owner_user_id=asset_scope.owner_user_id,
        limit=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES + 1,
    )
    if len(scenes) > DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES:
        raise ApplicationError(
            ApplicationErrorKind.UNAVAILABLE,
            "Managed Scene catalog exceeds the server limit.",
        )
    return [
        scene_to_dict(
            scene,
            git_config=(
                None if scene_git_configs is None else scene_git_configs.get(scene.asset_key)
            ),
        )
        for scene in scenes
    ]


async def create_managed_scene(
    scope: AdminScopeRef,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
    *,
    name: str,
    description: str,
    status: str = "enabled",
    source: str = "admin",
    required_skill_asset_key: str = "",
    recommended_skill_asset_keys: tuple[str, ...] = (),
) -> dict[str, object]:
    scene_name = validate_scene_name(name)
    actor = AuditActor.admin_user(session_user.user.id)
    storage_scope, asset_scope = await tenant_storage_and_asset_scope(
        scope,
        session_user,
        org_repository,
        permission_code="scenes.edit",
    )
    await ensure_scene_name_available(asset_repository, asset_scope, scene_name)
    asset_key = new_scene_asset_key()
    root = scene_content_path(scene_name)
    await require_asset_directory_absent(repository, storage_scope, root, "Scene")
    target = await managed_asset_mutation_path(repository, storage_scope, root)
    async with remove_directory_created_on_error(
        target,
        mutation_lock=repository.serialize_mutation(storage_scope),
    ):
        await repository.create_directory_async(storage_scope, root)
        asset = await asset_repository.save_scene(
            WorkspaceSceneAsset(
                tenant_id=asset_scope.tenant_id,
                scope_type=asset_scope.scope_type,
                owner_user_id=asset_scope.owner_user_id,
                asset_key=asset_key,
                name=scene_name,
                description=description,
                status=status,
                source=source,
                required_skill_asset_key=required_skill_asset_key,
                recommended_skill_asset_keys=recommended_skill_asset_keys,
                created_by_actor=actor,
                updated_by_actor=actor,
            )
        )
    return scene_to_dict(asset)


async def create_managed_scene_from_package(
    scope: AdminScopeRef,
    content: PackageContent,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
    *,
    name: str,
) -> dict[str, object]:
    scene_name = validate_scene_name(name)
    actor = AuditActor.admin_user(session_user.user.id)
    storage_scope, asset_scope = await tenant_storage_and_asset_scope(
        scope,
        session_user,
        org_repository,
        permission_code="scenes.edit",
    )
    await ensure_scene_name_available(asset_repository, asset_scope, scene_name)
    asset_key = new_scene_asset_key()
    max_bytes = repository.max_scene_package_bytes
    if await package_content_size_async(content) > max_bytes:
        raise ApplicationError(
            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
            f"Uploaded Scene package exceeds {max_bytes} bytes.",
        )
    await run_file_task(validate_package_content, content, max_bytes, "Scene")
    root = scene_content_path(scene_name)
    await require_asset_directory_absent(repository, storage_scope, root, "Scene")
    target = await managed_asset_mutation_path(repository, storage_scope, root)
    async with remove_directory_created_on_error(
        target,
        mutation_lock=repository.serialize_mutation(storage_scope),
    ):
        await repository.create_directory_async(storage_scope, root)
        created_target = await repository.resolve_managed_directory_async(storage_scope, root)
        if created_target is None:
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND,
                "Scene directory does not exist.",
            )
        entry = await run_file_mutation(
            replace_managed_directory_with_package,
            created_target,
            root,
            content,
            max_bytes,
            package_kind="Scene",
        )
        asset = await asset_repository.save_scene(
            WorkspaceSceneAsset(
                tenant_id=asset_scope.tenant_id,
                scope_type=asset_scope.scope_type,
                owner_user_id=asset_scope.owner_user_id,
                asset_key=asset_key,
                name=scene_name,
                source="upload",
                created_by_actor=actor,
                updated_by_actor=actor,
            )
        )
    return {**scene_to_dict(asset), "entry": entry.model_dump(mode="json")}


async def update_managed_scene(
    scope: AdminScopeRef,
    asset_key: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
    *,
    name: str | None,
    description: str | None,
    status: str | None,
    source: str | None,
    required_skill_asset_key: str | None,
    recommended_skill_asset_keys: tuple[str, ...] | None,
) -> dict[str, object]:
    context = await managed_scene_context(
        scope,
        asset_key,
        session_user,
        org_repository,
        asset_repository,
    )
    current = context.current
    scene_name = validate_scene_name(current.name if name is None else name)
    await ensure_scene_name_available(
        asset_repository,
        context.asset_scope,
        scene_name,
        current_asset_key=asset_key,
    )
    current_root = scene_content_path(current.name)
    next_root = scene_content_path(scene_name)
    current_target = await managed_asset_mutation_path(
        repository, context.storage_scope, current_root
    )
    next_target = await managed_asset_mutation_path(repository, context.storage_scope, next_root)
    async with restore_directory_on_error(
        current_target,
        cleanup_paths=(next_target,),
        mutation_lock=repository.serialize_mutation(context.storage_scope),
    ):
        if scene_name != current.name:
            try:
                await repository.move_path_async(context.storage_scope, current_root, next_root)
            except FileNotFoundError:
                pass
        await repository.create_directory_async(context.storage_scope, next_root)
        asset = await asset_repository.save_scene(
            current.model_copy(
                update={
                    "name": scene_name,
                    "description": current.description if description is None else description,
                    "status": current.status if status is None else status,
                    "source": (
                        "git"
                        if current.source == "git"
                        else current.source if source is None else source
                    ),
                    "required_skill_asset_key": (
                        current.required_skill_asset_key
                        if required_skill_asset_key is None
                        else required_skill_asset_key
                    ),
                    "recommended_skill_asset_keys": (
                        current.recommended_skill_asset_keys
                        if recommended_skill_asset_keys is None
                        else recommended_skill_asset_keys
                    ),
                    "updated_by_actor": context.actor,
                }
            )
        )
    return scene_to_dict(asset)


async def replace_managed_scene_package(
    scope: AdminScopeRef,
    asset_key: str,
    content: PackageContent,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> dict[str, object]:
    context = await managed_scene_context(
        scope, asset_key, session_user, org_repository, asset_repository
    )
    ensure_scene_content_writable(context.current)
    max_bytes = repository.max_scene_package_bytes
    if await package_content_size_async(content) > max_bytes:
        raise ApplicationError(
            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
            f"Uploaded Scene package exceeds {max_bytes} bytes.",
        )
    root = scene_content_path(context.current.name)
    target = await managed_asset_mutation_path(repository, context.storage_scope, root)
    async with restore_directory_on_error(
        target,
        mutation_lock=repository.serialize_mutation(context.storage_scope),
    ):
        await repository.create_directory_async(context.storage_scope, root)
        entry = await run_file_mutation(
            replace_managed_directory_with_package,
            target,
            root,
            content,
            max_bytes,
            package_kind="Scene",
        )
        asset = await asset_repository.save_scene(
            context.current.model_copy(
                update={"source": "upload", "updated_by_actor": context.actor}
            )
        )
    return {**scene_to_dict(asset), "entry": entry.model_dump(mode="json")}


async def delete_managed_scene(
    scope: AdminScopeRef,
    asset_key: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
    scene_git_repository: WorkspaceSceneGitRepository | None = None,
) -> None:
    context = await managed_scene_context(
        scope, asset_key, session_user, org_repository, asset_repository
    )
    target = await repository.resolve_managed_path_async(
        context.storage_scope,
        scene_content_path(context.current.name),
    )
    async with quarantine_path_until_success(
        target,
        mutation_lock=repository.serialize_mutation(context.storage_scope),
    ):
        if context.current.source == "git":
            if scene_git_repository is None:
                raise ApplicationError(
                    ApplicationErrorKind.UNAVAILABLE,
                    "Scene Git repository is unavailable.",
                )
            deleted = await scene_git_repository.delete_scene_asset_and_config(
                tenant_id=context.asset_scope.tenant_id,
                scope_type=context.asset_scope.scope_type,
                owner_user_id=context.asset_scope.owner_user_id,
                scene_asset_key=asset_key,
                updated_by_actor=context.actor,
            )
        else:
            deleted = await asset_repository.mark_scene_deleted(
                tenant_id=context.asset_scope.tenant_id,
                scope_type=context.asset_scope.scope_type,
                owner_user_id=context.asset_scope.owner_user_id,
                asset_key=asset_key,
                updated_by_actor=context.actor,
            )
        if not deleted:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Scene does not exist.")
