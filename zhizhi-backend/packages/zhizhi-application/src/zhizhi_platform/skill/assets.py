"""致知 tenant Skill asset use cases."""

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
from zhizhi_platform.iam import AdminScopeRef, AdminSessionUser
from zhizhi_platform.iam.ports import AdminOrgReadRepository
from zhizhi_platform.workspace.manifest_sync import SkillManifestSynchronizer
from zhizhi_platform.workspace.models import (
    ManagedWorkspaceRepository,
    WorkspaceAssetRepository,
    WorkspaceSkillAsset,
)
from zhizhi_platform.workspace.packages import (
    package_content_size_async,
    package_skill_manifest,
    replace_managed_directory_with_package,
    validated_asset_skill_content,
)
from zhizhi_platform.workspace.policy import (
    DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
    ensure_skill_name_available,
    managed_asset_mutation_path,
    managed_skill_context,
    new_skill_asset_key,
    require_asset_directory_absent,
    skill_content_path,
    skill_detail_to_dict,
    skill_file_path,
    skill_to_dict,
    tenant_storage_and_asset_scope,
    validate_skill_name,
)


async def list_managed_skills(
    scope: AdminScopeRef,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
) -> list[dict[str, object]]:
    _, asset_scope = await tenant_storage_and_asset_scope(
        scope,
        session_user,
        org_repository,
        permission_code="skills.view",
    )
    skills = await asset_repository.list_skills_by_scope(
        asset_scope.tenant_id,
        scope_type=asset_scope.scope_type,
        owner_user_id=asset_scope.owner_user_id,
        limit=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES + 1,
    )
    if len(skills) > DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES:
        raise ApplicationError(
            ApplicationErrorKind.UNAVAILABLE,
            "Managed Skill catalog exceeds the server limit.",
        )
    return [skill_to_dict(skill) for skill in skills]


async def get_managed_skill(
    scope: AdminScopeRef,
    asset_key: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> dict[str, object]:
    storage_scope, asset_scope = await tenant_storage_and_asset_scope(
        scope,
        session_user,
        org_repository,
        permission_code="skills.view",
    )
    asset = await asset_repository.get_skill(
        tenant_id=asset_scope.tenant_id,
        scope_type=asset_scope.scope_type,
        owner_user_id=asset_scope.owner_user_id,
        asset_key=asset_key,
    )
    if asset is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Skill does not exist.")
    file = await repository.read_file(storage_scope, skill_file_path(asset.name))
    if file is None:
        raise ApplicationError(
            ApplicationErrorKind.NOT_FOUND,
            "Skill content does not exist.",
        )
    return skill_detail_to_dict(asset, file)


async def create_managed_skill(
    scope: AdminScopeRef,
    content: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
    *,
    name: str = "",
    description: str = "",
    status: str = "enabled",
    source: str = "admin",
) -> dict[str, object]:
    asset_key = new_skill_asset_key()
    skill_name = validate_skill_name(name or asset_key)
    actor = AuditActor.admin_user(session_user.user.id)
    storage_scope, asset_scope = await tenant_storage_and_asset_scope(
        scope,
        session_user,
        org_repository,
        permission_code="skills.edit",
    )
    await ensure_skill_name_available(asset_repository, asset_scope, skill_name)
    normalized_content, manifest = validated_asset_skill_content(
        content,
        name=skill_name,
        description=description,
    )
    root_path = skill_content_path(skill_name)
    await require_asset_directory_absent(repository, storage_scope, root_path)
    target = await managed_asset_mutation_path(repository, storage_scope, root_path)
    async with remove_directory_created_on_error(
        target,
        mutation_lock=repository.serialize_mutation(storage_scope),
    ):
        await repository.create_directory_async(storage_scope, root_path)
        file = await repository.write_file(
            storage_scope,
            skill_file_path(skill_name),
            normalized_content,
        )
        asset = await SkillManifestSynchronizer(asset_repository).synchronize(
            manifest,
            tenant_id=asset_scope.tenant_id,
            scope_type=asset_scope.scope_type,
            owner_user_id=asset_scope.owner_user_id,
            actor=actor,
            source=source,
            status=status,
            current=WorkspaceSkillAsset(
                tenant_id=asset_scope.tenant_id,
                scope_type=asset_scope.scope_type,
                owner_user_id=asset_scope.owner_user_id,
                asset_key=asset_key,
                name=skill_name,
                created_by_actor=actor,
                updated_by_actor=actor,
            ),
        )
    return skill_detail_to_dict(asset, file)


async def create_managed_skill_from_package(
    scope: AdminScopeRef,
    content: PackageContent,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
    *,
    name: str,
    status: str = "enabled",
) -> dict[str, object]:
    asset_key = new_skill_asset_key()
    skill_name = validate_skill_name(name or asset_key)
    actor = AuditActor.admin_user(session_user.user.id)
    storage_scope, asset_scope = await tenant_storage_and_asset_scope(
        scope,
        session_user,
        org_repository,
        permission_code="skills.edit",
    )
    await ensure_skill_name_available(asset_repository, asset_scope, skill_name)
    max_bytes = repository.max_skill_package_bytes
    if await package_content_size_async(content) > max_bytes:
        raise ApplicationError(
            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
            f"Uploaded Skill package exceeds {max_bytes} bytes.",
        )
    manifest = await run_file_task(package_skill_manifest, content, max_bytes, skill_name)
    root_path = skill_content_path(skill_name)
    await require_asset_directory_absent(repository, storage_scope, root_path)
    target = await managed_asset_mutation_path(repository, storage_scope, root_path)
    async with remove_directory_created_on_error(
        target,
        mutation_lock=repository.serialize_mutation(storage_scope),
    ):
        await repository.create_directory_async(storage_scope, root_path)
        created_target = await repository.resolve_managed_directory_async(storage_scope, root_path)
        if created_target is None:
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND,
                "Skill directory does not exist.",
            )
        entry = await run_file_mutation(
            replace_managed_directory_with_package,
            created_target,
            root_path,
            content,
            max_bytes,
            require_skill_main_file=True,
        )
        asset = await SkillManifestSynchronizer(asset_repository).synchronize(
            manifest,
            tenant_id=asset_scope.tenant_id,
            scope_type=asset_scope.scope_type,
            owner_user_id=asset_scope.owner_user_id,
            actor=actor,
            source="upload",
            status=status,
            current=WorkspaceSkillAsset(
                tenant_id=asset_scope.tenant_id,
                scope_type=asset_scope.scope_type,
                owner_user_id=asset_scope.owner_user_id,
                asset_key=asset_key,
                name=skill_name,
                created_by_actor=actor,
                updated_by_actor=actor,
            ),
        )
    file = await repository.read_file(storage_scope, skill_file_path(asset.name))
    if file is None:
        raise ApplicationError(
            ApplicationErrorKind.NOT_FOUND,
            "Skill content does not exist.",
        )
    return {**skill_detail_to_dict(asset, file), "entry": entry.model_dump(mode="json")}


async def update_managed_skill(
    scope: AdminScopeRef,
    asset_key: str,
    content: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
    *,
    name: str = "",
    description: str = "",
    status: str = "enabled",
    source: str = "admin",
) -> dict[str, object]:
    context = await managed_skill_context(
        scope,
        asset_key,
        session_user,
        org_repository,
        asset_repository,
    )
    current = context.current
    skill_name = validate_skill_name(name or current.name)
    await ensure_skill_name_available(
        asset_repository,
        context.asset_scope,
        skill_name,
        current_asset_key=asset_key,
    )
    normalized_content, manifest = validated_asset_skill_content(
        content,
        name=skill_name,
        description=description,
    )
    current_root = skill_content_path(current.name)
    next_root = skill_content_path(skill_name)
    current_target = await managed_asset_mutation_path(
        repository,
        context.storage_scope,
        current_root,
    )
    next_target = await managed_asset_mutation_path(
        repository,
        context.storage_scope,
        next_root,
    )
    async with restore_directory_on_error(
        current_target,
        cleanup_paths=(next_target,),
        mutation_lock=repository.serialize_mutation(context.storage_scope),
    ):
        if skill_name != current.name:
            try:
                await repository.move_path_async(
                    context.storage_scope,
                    current_root,
                    next_root,
                )
            except FileNotFoundError:
                pass
        await repository.create_directory_async(context.storage_scope, next_root)
        file = await repository.write_file(
            context.storage_scope,
            skill_file_path(skill_name),
            normalized_content,
        )
        asset = await SkillManifestSynchronizer(asset_repository).synchronize(
            manifest,
            tenant_id=context.asset_scope.tenant_id,
            scope_type=context.asset_scope.scope_type,
            owner_user_id=context.asset_scope.owner_user_id,
            actor=context.actor,
            source=source,
            status=status,
            current=current,
        )
    return skill_detail_to_dict(asset, file)


async def delete_managed_skill(
    scope: AdminScopeRef,
    asset_key: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> None:
    context = await managed_skill_context(
        scope,
        asset_key,
        session_user,
        org_repository,
        asset_repository,
    )
    target = await repository.resolve_managed_path_async(
        context.storage_scope,
        skill_content_path(context.current.name),
    )
    async with quarantine_path_until_success(
        target,
        mutation_lock=repository.serialize_mutation(context.storage_scope),
    ):
        deleted = await asset_repository.mark_skill_deleted(
            tenant_id=context.asset_scope.tenant_id,
            scope_type=context.asset_scope.scope_type,
            owner_user_id=context.asset_scope.owner_user_id,
            asset_key=asset_key,
            updated_by_actor=context.actor,
        )
        if not deleted:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Skill does not exist.")


async def replace_managed_skill_package(
    scope: AdminScopeRef,
    asset_key: str,
    content: PackageContent,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    repository: ManagedWorkspaceRepository,
) -> dict[str, object]:
    context = await managed_skill_context(
        scope,
        asset_key,
        session_user,
        org_repository,
        asset_repository,
    )
    max_bytes = repository.max_skill_package_bytes
    if await package_content_size_async(content) > max_bytes:
        raise ApplicationError(
            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
            f"Uploaded Skill package exceeds {max_bytes} bytes.",
        )
    manifest = await run_file_task(package_skill_manifest, content, max_bytes)
    new_name = manifest.descriptor.name
    await ensure_skill_name_available(
        asset_repository,
        context.asset_scope,
        new_name,
        current_asset_key=asset_key,
    )
    current_root = skill_content_path(context.current.name)
    new_root = skill_content_path(new_name)
    current_target = await managed_asset_mutation_path(
        repository,
        context.storage_scope,
        current_root,
    )
    new_target = await managed_asset_mutation_path(
        repository,
        context.storage_scope,
        new_root,
    )
    if new_name != context.current.name and await run_file_task(new_target.exists):
        raise ApplicationError(ApplicationErrorKind.CONFLICT, "Skill directory already exists.")
    async with restore_directory_on_error(
        current_target,
        cleanup_paths=(new_target,),
        mutation_lock=repository.serialize_mutation(context.storage_scope),
    ):
        await repository.create_directory_async(context.storage_scope, current_root)
        entry = await run_file_mutation(
            replace_managed_directory_with_package,
            current_target,
            new_root,
            content,
            max_bytes,
            require_skill_main_file=True,
        )
        if new_name != context.current.name:
            await repository.move_path_async(
                context.storage_scope,
                current_root,
                new_root,
            )
        asset = await SkillManifestSynchronizer(asset_repository).synchronize(
            manifest,
            tenant_id=context.asset_scope.tenant_id,
            scope_type=context.asset_scope.scope_type,
            owner_user_id=context.asset_scope.owner_user_id,
            actor=context.actor,
            source="upload",
            current=context.current,
        )
    file = await repository.read_file(context.storage_scope, skill_file_path(asset.name))
    if file is None:
        raise ApplicationError(
            ApplicationErrorKind.NOT_FOUND,
            "Skill content does not exist.",
        )
    return {**skill_detail_to_dict(asset, file), "entry": entry.model_dump(mode="json")}
