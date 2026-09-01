"""Zhizhi Admin managed Skill file-tree use cases."""

from __future__ import annotations

from pathlib import Path

from gewu_agent_runtime.skill_contracts import ParsedSkillManifest
from gewu_core.archive import PackageContent
from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.file_locks import filesystem_mutation_lock
from gewu_core.file_tasks import FileTaskLane, run_file_mutation, run_file_task
from gewu_core.file_transactions import restore_directory_on_error
from gewu_core.filesystem import remove_path, replace_directory_with_staging
from zhizhi_platform.audit import AuditActor
from zhizhi_platform.iam import AdminScopeRef, AdminSessionUser
from zhizhi_platform.iam.ports import AdminOrgReadRepository
from zhizhi_platform.workspace.errors import ConflictError
from zhizhi_platform.workspace.manifest_sync import (
    SkillManifestSynchronizer,
    skill_name_from_main_path,
)
from zhizhi_platform.workspace.models import (
    ManagedFileEntry,
    ManagedWorkspaceRepository,
    WorkspaceAssetRepository,
)
from zhizhi_platform.workspace.packages import (
    cleanup_prepared_directory_replacement,
    managed_directory_entry,
    package_content_size_async,
    prepare_managed_directory_package,
)
from zhizhi_platform.workspace.policy import (
    MAX_UPLOAD_REPLACE_BYTES,
    hydrate_content_scope,
    normalize_skill_path,
    require_inline_preview_size,
    require_manage_scope,
    require_skill_asset_child_path,
    skill_root_mutation_path,
)


async def hydrate_skill_scope(
    scope: AdminScopeRef,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    permission_code: str,
) -> AdminScopeRef:
    from zhizhi_platform.iam import AdminScopeType

    if scope.scope_type is not AdminScopeType.TENANT:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Skill assets only support tenant scope.",
        )
    hydrated = await hydrate_content_scope(scope, org_repository)
    require_manage_scope(session_user, hydrated, permission_code)
    return hydrated


async def list_skill_entries(
    scope: AdminScopeRef,
    path: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    repository: ManagedWorkspaceRepository,
) -> list[dict[str, object]]:
    path = normalize_skill_path(path or ".skills", allow_root=True)
    scope = await hydrate_skill_scope(scope, session_user, org_repository, "skills.view")
    try:
        entries = await repository.list_entries(scope, path, include_skills=True)
    except FileNotFoundError:
        return []
    return [entry.model_dump(mode="json") for entry in entries]


async def read_skill_file(
    scope: AdminScopeRef,
    path: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    repository: ManagedWorkspaceRepository,
) -> dict[str, object]:
    path = normalize_skill_path(path, allow_root=False)
    scope = await hydrate_skill_scope(scope, session_user, org_repository, "skills.view")
    await require_inline_preview_size(scope, path, repository)
    file = await repository.read_file(scope, path)
    if file is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "File does not exist.")
    return file.model_dump(mode="json")


async def write_skill_file(
    scope: AdminScopeRef,
    path: str,
    content: str,
    expected_version: int | None,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    repository: ManagedWorkspaceRepository,
    asset_repository: WorkspaceAssetRepository,
) -> dict[str, object]:
    path = normalize_skill_path(path, allow_root=False)
    require_skill_asset_child_path(path)
    scope = await hydrate_skill_scope(scope, session_user, org_repository, "skills.edit")
    root_target = await skill_root_mutation_path(scope, path, repository)
    manifest = _validated_main_content(path, content)

    async def mutate() -> dict[str, object]:
        try:
            result = await repository.write_file(
                scope,
                path,
                content,
                expected_version=expected_version,
            )
        except ConflictError as exc:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, str(exc)) from exc
        if manifest is not None:
            await _sync_admin_skill_asset(
                scope,
                session_user,
                asset_repository,
                manifest,
                source="admin",
            )
        return result.model_dump(mode="json")

    mutation_guard = (
        restore_directory_on_error(
            root_target,
            mutation_lock=repository.serialize_mutation(scope),
        )
        if manifest is not None
        else filesystem_mutation_lock((root_target,))
    )
    async with mutation_guard:
        return await mutate()


async def resolve_skill_managed_path(
    scope: AdminScopeRef,
    path: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    repository: ManagedWorkspaceRepository,
) -> Path:
    path = normalize_skill_path(path, allow_root=True)
    scope = await hydrate_skill_scope(scope, session_user, org_repository, "skills.view")
    target = await repository.resolve_managed_path_async(scope, path)
    if target is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Path does not exist.")
    return target


async def replace_skill_file_bytes(
    scope: AdminScopeRef,
    path: str,
    content: bytes,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    repository: ManagedWorkspaceRepository,
    asset_repository: WorkspaceAssetRepository,
) -> ManagedFileEntry:
    path = normalize_skill_path(path, allow_root=False)
    require_skill_asset_child_path(path)
    if len(content) > MAX_UPLOAD_REPLACE_BYTES:
        raise ApplicationError(
            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
            "Uploaded file exceeds 10 MB limit.",
        )
    scope = await hydrate_skill_scope(scope, session_user, org_repository, "skills.edit")
    root_target = await skill_root_mutation_path(scope, path, repository)
    manifest = None
    if skill_name_from_main_path(path) is not None:
        try:
            manifest = SkillManifestSynchronizer.prepare_main_content(
                path,
                content.decode("utf-8"),
            )
        except UnicodeDecodeError as exc:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Skill file must be valid UTF-8 text.",
            ) from exc
        except ValueError as exc:
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, str(exc)) from exc

    async def mutate() -> ManagedFileEntry:
        entry = await repository.replace_file_bytes_async(scope, path, content)
        if manifest is not None:
            await _sync_admin_skill_asset(
                scope,
                session_user,
                asset_repository,
                manifest,
                source="upload",
            )
        return entry

    mutation_guard = (
        restore_directory_on_error(
            root_target,
            mutation_lock=repository.serialize_mutation(scope),
        )
        if manifest is not None
        else filesystem_mutation_lock((root_target,))
    )
    async with mutation_guard:
        async with repository.serialize_mutation(scope):
            return await mutate()


async def replace_skill_package_bytes(
    scope: AdminScopeRef,
    path: str,
    content: PackageContent,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    repository: ManagedWorkspaceRepository,
) -> ManagedFileEntry:
    path = normalize_skill_path(path, allow_root=False)
    require_skill_asset_child_path(path)
    max_bytes = repository.max_skill_package_bytes
    if await package_content_size_async(content) > max_bytes:
        raise ApplicationError(
            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
            f"Uploaded Skill package exceeds {max_bytes} bytes limit.",
        )
    scope = await hydrate_skill_scope(scope, session_user, org_repository, "skills.edit")
    root_target = await skill_root_mutation_path(scope, path, repository)
    async with filesystem_mutation_lock((root_target,)):
        scope = await hydrate_content_scope(scope, org_repository)
        require_manage_scope(session_user, scope, "skills.edit")
        target = await repository.resolve_managed_path_async(scope, path)
        if target is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Path does not exist.")
        if not await run_file_task(target.is_dir, lane=FileTaskLane.INTERACTIVE):
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Target path must be a directory.",
            )
        prepared = await run_file_task(
            prepare_managed_directory_package,
            target,
            content,
            max_bytes,
            cancel_result_cleanup=lambda result: remove_path(result.staging_path),
        )
        backup: Path | None = None
        try:
            async with repository.serialize_mutation(scope):
                backup = await run_file_task(
                    replace_directory_with_staging,
                    prepared.staging_path,
                    target,
                    wait_on_cancel=True,
                    cancel_result_cleanup=lambda result: cleanup_prepared_directory_replacement(
                        prepared.staging_path,
                        result,
                    ),
                )
            return await run_file_task(
                managed_directory_entry,
                target,
                path,
                prepared.size_bytes,
                lane=FileTaskLane.INTERACTIVE,
            )
        finally:
            await run_file_mutation(
                cleanup_prepared_directory_replacement,
                prepared.staging_path,
                backup,
            )


async def create_skill_directory(
    scope: AdminScopeRef,
    path: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    repository: ManagedWorkspaceRepository,
) -> None:
    path = normalize_skill_path(path, allow_root=False)
    require_skill_asset_child_path(path)
    scope = await hydrate_skill_scope(scope, session_user, org_repository, "skills.edit")
    root_target = await skill_root_mutation_path(scope, path, repository)
    async with (
        filesystem_mutation_lock((root_target,)),
        repository.serialize_mutation(scope),
    ):
        await repository.create_directory_async(scope, path)


async def move_skill_path(
    scope: AdminScopeRef,
    src_path: str,
    dst_path: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    repository: ManagedWorkspaceRepository,
) -> None:
    src_path = normalize_skill_path(src_path, allow_root=False)
    dst_path = normalize_skill_path(dst_path, allow_root=False)
    require_skill_asset_child_path(src_path)
    require_skill_asset_child_path(dst_path)
    if (
        skill_name_from_main_path(src_path) is not None
        or skill_name_from_main_path(dst_path) is not None
    ):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Move or rename a Skill through the Skill asset editor so SKILL.md stays consistent.",
        )
    scope = await hydrate_skill_scope(scope, session_user, org_repository, "skills.edit")
    src_root = await skill_root_mutation_path(scope, src_path, repository)
    dst_root = await skill_root_mutation_path(scope, dst_path, repository)
    async with (
        filesystem_mutation_lock((src_root, dst_root)),
        repository.serialize_mutation(scope),
    ):
        await repository.move_path_async(scope, src_path, dst_path)


async def delete_skill_path(
    scope: AdminScopeRef,
    path: str,
    recursive: bool,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    repository: ManagedWorkspaceRepository,
) -> None:
    path = normalize_skill_path(path, allow_root=False)
    require_skill_asset_child_path(path)
    if skill_name_from_main_path(path) is not None:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "SKILL.md cannot be deleted separately from its Skill.",
        )
    scope = await hydrate_skill_scope(scope, session_user, org_repository, "skills.edit")
    root_target = await skill_root_mutation_path(scope, path, repository)
    async with (
        filesystem_mutation_lock((root_target,)),
        repository.serialize_mutation(scope),
    ):
        await repository.delete_path_async(scope, path, recursive=recursive)


def _validated_main_content(
    path: str,
    content: str,
) -> ParsedSkillManifest | None:
    try:
        return SkillManifestSynchronizer.prepare_main_content(path, content)
    except ValueError as exc:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, str(exc)) from exc


async def _sync_admin_skill_asset(
    scope: AdminScopeRef,
    session_user: AdminSessionUser,
    asset_repository: WorkspaceAssetRepository,
    manifest: ParsedSkillManifest,
    *,
    source: str,
) -> None:
    await SkillManifestSynchronizer(asset_repository).synchronize(
        manifest,
        tenant_id=scope.scope_tenant_id,
        scope_type="tenant",
        owner_user_id=None,
        actor=AuditActor.admin_user(session_user.user.id),
        source=source,
    )
