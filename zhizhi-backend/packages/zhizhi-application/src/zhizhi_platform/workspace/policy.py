"""致知 Skill and Scene scope, identity, and presentation policy."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.ids import new_uuid4_id
from zhizhi_platform.audit import AuditActor
from zhizhi_platform.git import WorkspaceSceneGitConfig
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
)
from zhizhi_platform.iam.ports import AdminOrgReadRepository
from zhizhi_platform.workspace.files import ManagedWorkspacePath
from zhizhi_platform.workspace.models import (
    ManagedFileEntry,
    ManagedTextFile,
    ManagedWorkspaceRepository,
    WorkspaceAssetRepository,
    WorkspaceSceneAsset,
    WorkspaceSceneAssetRepository,
    WorkspaceSkillAsset,
)

ASSET_KEY_RE = re.compile(r"^(skill|scene)_[a-f0-9]{32}$")
SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SKILL_ASSET_PREFIX = "skill"
SCENE_ASSET_PREFIX = "scene"
SKILL_ROOT = ".skills"
SCENE_ROOT = ".scenes"
SKILL_MAIN_FILE = "SKILL.md"
MAX_UPLOAD_REPLACE_BYTES = 10 * 1024 * 1024
MAX_INLINE_FILE_BYTES = 1024 * 1024
DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES = 1000


class ManagedAssetScope(BaseModel):
    """Normalized exact metadata scope for one 致知 managed asset."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    scope_type: str
    owner_user_id: str | None = None


class ManagedSkillContext(BaseModel):
    """Authorized edit context for one tenant Skill asset."""

    model_config = ConfigDict(frozen=True)

    actor: AuditActor
    storage_scope: AdminScopeRef
    asset_scope: ManagedAssetScope
    current: WorkspaceSkillAsset


class ManagedSceneContext(BaseModel):
    """Authorized 致知 tenant Scene context."""

    model_config = ConfigDict(frozen=True)

    actor: AuditActor
    storage_scope: AdminScopeRef
    asset_scope: ManagedAssetScope
    current: WorkspaceSceneAsset


def validate_skill_name(skill_name: str) -> str:
    normalized = skill_name.strip()
    if not SKILL_NAME_RE.fullmatch(normalized):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Skill name must start with a letter or digit and only contain letters, digits, '_' or '-'.",
        )
    return normalized


def validate_skill_asset_key(asset_key: str) -> None:
    if not ASSET_KEY_RE.fullmatch(asset_key) or not asset_key.startswith("skill_"):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Asset key must start with skill_ and be path-safe.",
        )


def validate_scene_asset_key(asset_key: str) -> None:
    if not ASSET_KEY_RE.fullmatch(asset_key) or not asset_key.startswith("scene_"):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Asset key must start with scene_ and be path-safe.",
        )


def validate_scene_name(scene_name: str) -> str:
    normalized = scene_name.strip()
    if not normalized or normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Scene name must be a non-empty path-safe directory name.",
        )
    return normalized


async def hydrate_content_scope(
    scope: AdminScopeRef,
    org_repository: AdminOrgReadRepository,
) -> AdminScopeRef:
    hydrated = await org_repository.hydrate_scope(scope)
    if not hydrated.scope_tenant_storage_key:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Tenant is not enabled for content storage.",
        )
    if (
        scope.scope_type is AdminScopeType.ORGANIZATION_UNIT
        and not hydrated.scope_organization_path
    ):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Organization unit is not active in this tenant.",
        )
    return hydrated


def normalize_content_path(path: str) -> str:
    if path == "":
        return ""
    try:
        normalized = ManagedWorkspacePath(value=path).value
    except ValueError as exc:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Invalid managed content path.",
        ) from exc
    if normalized.split("/", 1)[0] in {SKILL_ROOT, SCENE_ROOT}:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            ".skills and .scenes are managed by dedicated asset APIs.",
        )
    return normalized


def require_manage_scope(
    session_user: AdminSessionUser,
    scope: AdminScopeRef,
    permission_code: str,
) -> None:
    if session_user.is_super:
        return
    if permission_code not in session_user.permission_codes_for_scope(scope):
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            f"Missing scoped permission: {permission_code}",
        )


async def tenant_storage_and_asset_scope(
    scope: AdminScopeRef,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    *,
    permission_code: str,
) -> tuple[AdminScopeRef, ManagedAssetScope]:
    if scope.scope_type is not AdminScopeType.TENANT:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Skill and Scene assets only support tenant scope.",
        )
    hydrated = await hydrate_content_scope(scope, org_repository)
    require_manage_scope(session_user, hydrated, permission_code)
    return hydrated, ManagedAssetScope(
        tenant_id=hydrated.scope_tenant_id,
        scope_type="tenant",
        owner_user_id=None,
    )


async def managed_skill_context(
    scope: AdminScopeRef,
    asset_key: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
) -> ManagedSkillContext:
    validate_skill_asset_key(asset_key)
    storage_scope, asset_scope = await tenant_storage_and_asset_scope(
        scope,
        session_user,
        org_repository,
        permission_code="skills.edit",
    )
    current = await asset_repository.get_skill(
        tenant_id=asset_scope.tenant_id,
        scope_type=asset_scope.scope_type,
        owner_user_id=asset_scope.owner_user_id,
        asset_key=asset_key,
    )
    if current is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Skill does not exist.")
    return ManagedSkillContext(
        actor=AuditActor.admin_user(session_user.user.id),
        storage_scope=storage_scope,
        asset_scope=asset_scope,
        current=current,
    )


async def managed_scene_context(
    scope: AdminScopeRef,
    asset_key: str,
    session_user: AdminSessionUser,
    org_repository: AdminOrgReadRepository,
    asset_repository: WorkspaceAssetRepository,
    *,
    permission_code: str = "scenes.edit",
) -> ManagedSceneContext:
    validate_scene_asset_key(asset_key)
    storage_scope, asset_scope = await tenant_storage_and_asset_scope(
        scope,
        session_user,
        org_repository,
        permission_code=permission_code,
    )
    current = await asset_repository.get_scene(
        tenant_id=asset_scope.tenant_id,
        scope_type=asset_scope.scope_type,
        owner_user_id=asset_scope.owner_user_id,
        asset_key=asset_key,
    )
    if current is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Scene does not exist.")
    return ManagedSceneContext(
        actor=AuditActor.admin_user(session_user.user.id),
        storage_scope=storage_scope,
        asset_scope=asset_scope,
        current=current,
    )


async def ensure_skill_name_available(
    repository: WorkspaceAssetRepository,
    scope: ManagedAssetScope,
    skill_name: str,
    *,
    current_asset_key: str = "",
) -> None:
    if await repository.skill_name_exists(
        scope.tenant_id,
        scope_type=scope.scope_type,
        owner_user_id=scope.owner_user_id,
        name=skill_name,
        exclude_asset_key=current_asset_key,
    ):
        raise ApplicationError(ApplicationErrorKind.CONFLICT, "Skill name already exists.")


async def ensure_scene_name_available(
    repository: WorkspaceSceneAssetRepository,
    scope: ManagedAssetScope,
    scene_name: str,
    *,
    current_asset_key: str = "",
) -> None:
    if await repository.scene_name_exists(
        scope.tenant_id,
        scope_type=scope.scope_type,
        owner_user_id=scope.owner_user_id,
        name=scene_name,
        exclude_asset_key=current_asset_key,
    ):
        raise ApplicationError(ApplicationErrorKind.CONFLICT, "Scene name already exists.")


def new_skill_asset_key() -> str:
    return f"skill_{new_uuid4_id()}"


def new_scene_asset_key() -> str:
    return f"scene_{new_uuid4_id()}"


def skill_content_path(skill_name: str) -> str:
    return f"{SKILL_ROOT}/{skill_name}"


def skill_file_path(skill_name: str) -> str:
    return f"{skill_content_path(skill_name)}/{SKILL_MAIN_FILE}"


def scene_content_path(scene_name: str) -> str:
    return f"{SCENE_ROOT}/{scene_name}"


def skill_to_dict(asset: WorkspaceSkillAsset) -> dict[str, object]:
    return {
        "id": asset.id,
        "asset_key": asset.asset_key,
        "name": asset.name,
        "description": asset.description,
        "status": asset.status,
        "scope_type": asset.scope_type,
        "owner_user_id": asset.owner_user_id,
        "path": skill_content_path(asset.name),
        "source": asset.source,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }


def scene_to_dict(
    asset: WorkspaceSceneAsset,
    *,
    git_config: WorkspaceSceneGitConfig | None = None,
) -> dict[str, object]:
    source = asset.source or "admin"
    return {
        "id": asset.asset_key,
        "asset_key": asset.asset_key,
        "name": asset.name,
        "description": asset.description,
        "path": scene_content_path(asset.name),
        "mode": "auto",
        "status": asset.status,
        "source": source,
        "readonly": source == "git",
        "scope_type": asset.scope_type,
        "owner_user_id": asset.owner_user_id,
        "required_skill_asset_key": asset.required_skill_asset_key,
        "recommended_skill_asset_keys": list(asset.recommended_skill_asset_keys),
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
        "git": (_scene_git_config_to_public_dict(git_config) if git_config is not None else None),
    }


def _scene_git_config_to_public_dict(
    config: WorkspaceSceneGitConfig,
) -> dict[str, object]:
    return {
        "scene_asset_key": config.scene_asset_key,
        "git_repository_id": config.git_repository_id,
        "branch": config.branch,
        "ref": config.ref,
        "subdir": config.subdir,
        "auto_sync_enabled": config.auto_sync_enabled,
        "daily_sync_time": (
            config.daily_sync_time.isoformat(timespec="minutes") if config.daily_sync_time else ""
        ),
        "timezone": config.timezone,
        "next_sync_at": config.next_sync_at,
        "last_synced_at": config.last_synced_at,
        "last_commit_sha": config.last_commit_sha,
        "last_sync_status": config.last_sync_status,
        "last_sync_error": config.last_sync_error,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def skill_detail_to_dict(
    asset: WorkspaceSkillAsset,
    file: ManagedTextFile,
) -> dict[str, object]:
    return {
        **skill_to_dict(asset),
        "skill_name": asset.name,
        "layout": "directory",
        "main_file_path": file.path,
        "content": file.content,
        "version": str(file.version),
    }


async def require_asset_directory_absent(
    repository: ManagedWorkspaceRepository,
    scope: AdminScopeRef,
    path: str,
    asset_kind: str = "Skill",
) -> None:
    if await repository.resolve_managed_path_async(scope, path) is not None:
        raise ApplicationError(
            ApplicationErrorKind.CONFLICT,
            f"{asset_kind} directory already exists.",
        )


async def managed_asset_mutation_path(
    repository: ManagedWorkspaceRepository,
    scope: AdminScopeRef,
    path: str,
) -> Path:
    logical_path = PurePosixPath(path)
    parent_path = logical_path.parent.as_posix()
    parent = await repository.resolve_managed_directory_async(scope, parent_path)
    if parent is None:
        await repository.create_directory_async(scope, parent_path)
        parent = await repository.resolve_managed_directory_async(scope, parent_path)
    if parent is None:
        raise ApplicationError(
            ApplicationErrorKind.NOT_FOUND,
            "Asset parent directory does not exist.",
        )
    return parent / logical_path.name


def normalize_skill_path(path: str, *, allow_root: bool) -> str:
    normalized = str(PurePosixPath(path.replace("\\", "/").strip().strip("/")))
    if normalized in {"", "."}:
        normalized = SKILL_ROOT
    parts = PurePosixPath(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "Skill path is invalid.")
    if not parts or parts[0] != SKILL_ROOT:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Skill path must be under .skills.",
        )
    if not allow_root and normalized == SKILL_ROOT:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Operation cannot target the skills root.",
        )
    return normalized


def require_skill_asset_child_path(path: str) -> None:
    if len(PurePosixPath(path).parts) < 3:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Skill asset roots are managed by the Skill asset API.",
        )


async def skill_root_mutation_path(
    scope: AdminScopeRef,
    path: str,
    repository: ManagedWorkspaceRepository,
) -> Path:
    parts = PurePosixPath(path).parts
    root = await repository.resolve_managed_directory_async(scope, SKILL_ROOT)
    if root is None:
        raise ApplicationError(
            ApplicationErrorKind.NOT_FOUND,
            "Skills directory does not exist.",
        )
    return root / parts[1]


async def require_inline_preview_size(
    scope: AdminScopeRef,
    path: str,
    repository: ManagedWorkspaceRepository,
) -> None:
    entries = await repository.list_entries(scope, path, include_skills=True)
    matched = next((entry for entry in entries if entry.path == path), None)
    if matched is not None and matched.size_bytes > MAX_INLINE_FILE_BYTES:
        raise ApplicationError(
            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
            "File exceeds 1 MB inline preview limit.",
        )


async def require_inline_file_preview_size(
    scope: AdminScopeRef,
    path: str,
    repository: ManagedWorkspaceRepository,
    *,
    include_skills: bool,
) -> None:
    entries = await repository.list_entries(scope, path, include_skills=include_skills)
    matched = next((entry for entry in entries if entry.path == path), None)
    if matched is not None and matched.size_bytes > MAX_INLINE_FILE_BYTES:
        raise ApplicationError(
            ApplicationErrorKind.PAYLOAD_TOO_LARGE,
            "File exceeds 1 MB inline preview limit.",
        )


def ensure_scene_content_writable(asset: WorkspaceSceneAsset) -> None:
    if asset.source == "git":
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Git-backed Scene content is read-only. Use sync instead.",
        )


def normalize_relative_path(path: str) -> str:
    normalized = str(PurePosixPath(path.replace("\\", "/").strip().strip("/")))
    if normalized in {"", "."}:
        return ""
    if any(part in {"", ".", ".."} for part in PurePosixPath(normalized).parts):
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "Asset path is invalid.")
    return normalized


def asset_child_path(root_path: str, child_path: str) -> str:
    normalized = normalize_relative_path(child_path)
    return root_path if not normalized else f"{root_path.rstrip('/')}/{normalized}"


def require_scene_asset_child_path(path: str) -> None:
    if not normalize_relative_path(path):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Scene asset roots are managed by the Scene asset API.",
        )


def relative_asset_child_path(root_path: str, path: str) -> str:
    normalized = normalize_relative_path(path)
    root = root_path.strip("/")
    if normalized == root:
        return ""
    return normalized.removeprefix(f"{root}/")


def scene_entry_to_dict(root_path: str, entry: ManagedFileEntry) -> dict[str, object]:
    return {
        **entry.model_dump(mode="json"),
        "path": relative_asset_child_path(root_path, entry.path),
    }


def scene_file_to_dict(root_path: str, file: ManagedTextFile) -> dict[str, object]:
    return {
        **file.model_dump(mode="json"),
        "path": relative_asset_child_path(root_path, file.path),
    }


async def require_managed_asset_root(
    repository: ManagedWorkspaceRepository,
    scope: AdminScopeRef,
    path: str,
) -> Path:
    target = await repository.resolve_managed_directory_async(scope, path)
    if target is None:
        raise ApplicationError(
            ApplicationErrorKind.NOT_FOUND,
            "Asset directory does not exist.",
        )
    return target
