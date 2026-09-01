"""Zhizhi Admin managed Scene file-tree use cases."""

from __future__ import annotations

from pathlib import Path

from gewu_core.archive import PackageContent
from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.file_locks import filesystem_mutation_lock
from gewu_core.file_tasks import FileTaskLane, run_file_mutation, run_file_task
from zhizhi_platform.iam import AdminScopeRef, AdminSessionUser
from zhizhi_platform.iam.ports import AdminOrgReadRepository
from zhizhi_platform.workspace.errors import ConflictError
from zhizhi_platform.workspace.models import (
    ManagedWorkspaceRepository,
    WorkspaceAssetRepository,
)
from zhizhi_platform.workspace.packages import (
    package_content_size_async,
    replace_managed_directory_with_package,
)
from zhizhi_platform.workspace.policy import (
    MAX_UPLOAD_REPLACE_BYTES,
    asset_child_path,
    ensure_scene_content_writable,
    managed_scene_context,
    require_managed_asset_root,
    require_scene_asset_child_path,
    scene_content_path,
    scene_entry_to_dict,
    scene_file_to_dict,
)


async def list_managed_scene_entries(
    scope: AdminScopeRef,
    asset_key: str,
    path: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> list[dict[str, object]]:
    context = await managed_scene_context(
        scope,
        asset_key,
        session_user,
        org_repository,
        asset_repository,
        permission_code="scenes.view",
    )
    root = scene_content_path(context.current.name)
    entries = await repository.list_entries(
        context.storage_scope,
        asset_child_path(root, path),
        include_skills=True,
    )
    return [scene_entry_to_dict(root, entry) for entry in entries]


async def read_managed_scene_file(
    scope: AdminScopeRef,
    asset_key: str,
    path: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> dict[str, object]:
    context = await managed_scene_context(
        scope,
        asset_key,
        session_user,
        org_repository,
        asset_repository,
        permission_code="scenes.view",
    )
    root = scene_content_path(context.current.name)
    file = await repository.read_file(context.storage_scope, asset_child_path(root, path))
    if file is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Scene file does not exist.")
    return scene_file_to_dict(root, file)


async def write_managed_scene_file(
    scope: AdminScopeRef,
    asset_key: str,
    path: str,
    content: str,
    expected_version: int | None,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> dict[str, object]:
    context = await managed_scene_context(
        scope, asset_key, session_user, org_repository, asset_repository
    )
    ensure_scene_content_writable(context.current)
    require_scene_asset_child_path(path)
    root = scene_content_path(context.current.name)
    root_target = await require_managed_asset_root(repository, context.storage_scope, root)
    async with filesystem_mutation_lock((root_target,)):
        try:
            file = await repository.write_file(
                context.storage_scope,
                asset_child_path(root, path),
                content,
                expected_version=expected_version,
            )
        except ConflictError as exc:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, str(exc)) from exc
    return scene_file_to_dict(root, file)


async def resolve_managed_scene_path(
    scope: AdminScopeRef,
    asset_key: str,
    path: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> Path:
    context = await managed_scene_context(
        scope,
        asset_key,
        session_user,
        org_repository,
        asset_repository,
        permission_code="scenes.view",
    )
    target = await repository.resolve_managed_path_async(
        context.storage_scope,
        asset_child_path(scene_content_path(context.current.name), path),
    )
    if target is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Scene path does not exist.")
    return target


async def replace_managed_scene_file_bytes(
    scope: AdminScopeRef,
    asset_key: str,
    path: str,
    content: bytes,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> dict[str, object]:
    if len(content) > MAX_UPLOAD_REPLACE_BYTES:
        raise ApplicationError(
            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
            "Uploaded file exceeds 10 MB limit.",
        )
    context = await managed_scene_context(
        scope, asset_key, session_user, org_repository, asset_repository
    )
    ensure_scene_content_writable(context.current)
    require_scene_asset_child_path(path)
    root = scene_content_path(context.current.name)
    root_target = await require_managed_asset_root(repository, context.storage_scope, root)
    async with (
        filesystem_mutation_lock((root_target,)),
        repository.serialize_mutation(context.storage_scope),
    ):
        entry = await repository.replace_file_bytes_async(
            context.storage_scope,
            asset_child_path(root, path),
            content,
        )
    return scene_entry_to_dict(root, entry)


async def replace_managed_scene_directory_package(
    scope: AdminScopeRef,
    asset_key: str,
    path: str,
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
    require_scene_asset_child_path(path)
    max_bytes = repository.max_scene_package_bytes
    if await package_content_size_async(content) > max_bytes:
        raise ApplicationError(
            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
            f"Uploaded Scene package exceeds {max_bytes} bytes.",
        )
    root = scene_content_path(context.current.name)
    scene_path = asset_child_path(root, path)
    target = await repository.resolve_managed_path_async(context.storage_scope, scene_path)
    if target is None:
        raise ApplicationError(
            ApplicationErrorKind.NOT_FOUND,
            "Scene directory does not exist.",
        )
    if not await run_file_task(target.is_dir, lane=FileTaskLane.INTERACTIVE):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Target path must be a directory.",
        )
    root_target = await require_managed_asset_root(repository, context.storage_scope, root)
    async with (
        filesystem_mutation_lock((root_target,)),
        repository.serialize_mutation(context.storage_scope),
    ):
        entry = await run_file_mutation(
            replace_managed_directory_with_package,
            target,
            scene_path,
            content,
            max_bytes,
            package_kind="Scene",
        )
    return scene_entry_to_dict(root, entry)


async def create_managed_scene_directory(
    scope: AdminScopeRef,
    asset_key: str,
    path: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> None:
    context = await managed_scene_context(
        scope, asset_key, session_user, org_repository, asset_repository
    )
    ensure_scene_content_writable(context.current)
    require_scene_asset_child_path(path)
    root = scene_content_path(context.current.name)
    root_target = await require_managed_asset_root(repository, context.storage_scope, root)
    async with (
        filesystem_mutation_lock((root_target,)),
        repository.serialize_mutation(context.storage_scope),
    ):
        await repository.create_directory_async(
            context.storage_scope,
            asset_child_path(root, path),
        )


async def move_managed_scene_path(
    scope: AdminScopeRef,
    asset_key: str,
    src_path: str,
    dst_path: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> None:
    context = await managed_scene_context(
        scope, asset_key, session_user, org_repository, asset_repository
    )
    ensure_scene_content_writable(context.current)
    require_scene_asset_child_path(src_path)
    require_scene_asset_child_path(dst_path)
    root = scene_content_path(context.current.name)
    root_target = await require_managed_asset_root(repository, context.storage_scope, root)
    async with (
        filesystem_mutation_lock((root_target,)),
        repository.serialize_mutation(context.storage_scope),
    ):
        await repository.move_path_async(
            context.storage_scope,
            asset_child_path(root, src_path),
            asset_child_path(root, dst_path),
        )


async def delete_managed_scene_path(
    scope: AdminScopeRef,
    asset_key: str,
    path: str,
    recursive: bool,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> None:
    context = await managed_scene_context(
        scope, asset_key, session_user, org_repository, asset_repository
    )
    ensure_scene_content_writable(context.current)
    require_scene_asset_child_path(path)
    root = scene_content_path(context.current.name)
    root_target = await require_managed_asset_root(repository, context.storage_scope, root)
    async with (
        filesystem_mutation_lock((root_target,)),
        repository.serialize_mutation(context.storage_scope),
    ):
        await repository.delete_path_async(
            context.storage_scope,
            asset_child_path(root, path),
            recursive=recursive,
        )
