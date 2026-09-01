"""Zhizhi management use cases for Git-backed Scene assets."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta, tzinfo
from datetime import timezone as fixed_timezone
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.file_transactions import remove_directory_created_on_error
from gewu_core.ids import new_uuid4_id
from zhizhi_platform.audit import AuditActor
from zhizhi_platform.git import (
    ManagedGitRepository,
    WorkspaceSceneGitConfig,
    WorkspaceSceneGitRepository,
)
from zhizhi_platform.git.ports import AdminGitRepository
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
    ensure_admin_permission,
)
from zhizhi_platform.iam.ports import AdminOrgReadRepository
from zhizhi_platform.workspace.background_jobs import (
    BackgroundJob,
    BackgroundJobRepository,
    SceneGitSyncDispatcher,
)
from zhizhi_platform.workspace.models import (
    ManagedWorkspaceRepository,
    WorkspaceSceneAsset,
    WorkspaceSceneAssetRepository,
)
from zhizhi_platform.workspace.policy import (
    DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
    ManagedAssetScope,
    ensure_scene_name_available,
    managed_asset_mutation_path,
    new_scene_asset_key,
    require_asset_directory_absent,
    require_manage_scope,
    scene_content_path,
    scene_to_dict,
    tenant_storage_and_asset_scope,
    validate_scene_name,
)

SCENE_GIT_SOURCE = "git"
SCENE_GIT_JOB_TYPE = "scene_git_sync"
SCENE_JOB_TARGET_TYPE = "scene"
DEFAULT_SCENE_GIT_TIMEZONE = "Asia/Shanghai"
DEFAULT_SCENE_GIT_DAILY_TIME = time(hour=3)


class CreateGitSceneCommand(BaseModel):
    """Create one Git-backed Scene and its synchronization config."""

    model_config = ConfigDict(frozen=True)

    scope: AdminScopeRef
    session_user: AdminSessionUser
    name: str
    description: str = ""
    status: str = "enabled"
    required_skill_asset_key: str = ""
    recommended_skill_asset_keys: tuple[str, ...] = ()
    git_repository_id: str
    branch: str = ""
    ref: str = ""
    subdir: str = ""
    auto_sync_enabled: bool = False
    daily_sync_time: str = "03:00"
    timezone: str = DEFAULT_SCENE_GIT_TIMEZONE


class UpdateGitSceneConfigCommand(BaseModel):
    """Patch one Git-backed Scene synchronization config."""

    model_config = ConfigDict(frozen=True)

    scope: AdminScopeRef
    scene_asset_key: str
    session_user: AdminSessionUser
    git_repository_id: str | None = None
    branch: str | None = None
    ref: str | None = None
    subdir: str | None = None
    auto_sync_enabled: bool | None = None
    daily_sync_time: str | None = None
    timezone: str | None = None


class SceneGitAdminService:
    """Coordinate authorized Scene Git lifecycle and background dispatch."""

    def __init__(
        self,
        *,
        org_repository: AdminOrgReadRepository,
        asset_repository: WorkspaceSceneAssetRepository,
        git_repository: AdminGitRepository,
        scene_git_repository: WorkspaceSceneGitRepository,
        workspace_repository: ManagedWorkspaceRepository,
        job_repository: BackgroundJobRepository,
        dispatcher: SceneGitSyncDispatcher,
    ) -> None:
        self._org_repository = org_repository
        self._asset_repository = asset_repository
        self._git_repository = git_repository
        self._scene_git_repository = scene_git_repository
        self._workspace_repository = workspace_repository
        self._job_repository = job_repository
        self._dispatcher = dispatcher

    async def list_configs_by_asset_key(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
    ) -> dict[str, WorkspaceSceneGitConfig]:
        ensure_admin_permission(session_user, "scenes.view")
        _, asset_scope = await tenant_storage_and_asset_scope(
            scope,
            session_user,
            self._org_repository,
            permission_code="scenes.view",
        )
        configs = await self._scene_git_repository.list_configs_by_scope(
            tenant_id=asset_scope.tenant_id,
            scope_type=asset_scope.scope_type,
            owner_user_id=asset_scope.owner_user_id,
            limit=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES + 1,
        )
        if len(configs) > DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES:
            raise ApplicationError(
                ApplicationErrorKind.UNAVAILABLE,
                "Managed Scene Git configuration catalog exceeds the server limit.",
            )
        return {config.scene_asset_key: config for config in configs}

    async def create(self, command: CreateGitSceneCommand) -> dict[str, object]:
        ensure_admin_permission(command.session_user, "scenes.edit")
        daily_sync_time = parse_daily_sync_time(command.daily_sync_time)
        scene_name = validate_scene_name(command.name)
        actor = AuditActor.admin_user(command.session_user.user.id)
        storage_scope, asset_scope = await tenant_storage_and_asset_scope(
            command.scope,
            command.session_user,
            self._org_repository,
            permission_code="scenes.edit",
        )
        await ensure_scene_name_available(self._asset_repository, asset_scope, scene_name)
        asset_key = new_scene_asset_key()
        git_resource = await require_available_git_resource(
            asset_scope.tenant_id,
            command.git_repository_id,
            self._git_repository,
        )
        subdir = normalize_optional_relative_path(command.subdir)
        branch = command.branch.strip()
        ref = command.ref.strip()
        timezone = validate_timezone(command.timezone)
        root = scene_content_path(scene_name)
        await require_asset_directory_absent(
            self._workspace_repository,
            storage_scope,
            root,
            "Scene",
        )
        target = await managed_asset_mutation_path(
            self._workspace_repository,
            storage_scope,
            root,
        )
        asset_saved = False
        await self._workspace_repository.create_directory_async(storage_scope, root)
        async with remove_directory_created_on_error(
            target,
            mutation_lock=self._workspace_repository.serialize_mutation(storage_scope),
        ):
            try:
                asset = await self._asset_repository.save_scene(
                    WorkspaceSceneAsset(
                        tenant_id=asset_scope.tenant_id,
                        scope_type=asset_scope.scope_type,
                        owner_user_id=asset_scope.owner_user_id,
                        asset_key=asset_key,
                        name=scene_name,
                        description=command.description,
                        status=command.status,
                        source=SCENE_GIT_SOURCE,
                        required_skill_asset_key=command.required_skill_asset_key,
                        recommended_skill_asset_keys=command.recommended_skill_asset_keys,
                        created_by_actor=actor,
                        updated_by_actor=actor,
                    )
                )
                asset_saved = True
                config = await self._scene_git_repository.save_config(
                    WorkspaceSceneGitConfig(
                        tenant_id=asset_scope.tenant_id,
                        scope_type=asset_scope.scope_type,
                        owner_user_id=asset_scope.owner_user_id,
                        scene_asset_key=asset_key,
                        git_repository_id=git_resource.id,
                        branch=branch,
                        ref=ref,
                        subdir=subdir,
                        auto_sync_enabled=command.auto_sync_enabled,
                        daily_sync_time=daily_sync_time,
                        timezone=timezone,
                        next_sync_at=(
                            next_daily_sync_at(daily_sync_time, timezone)
                            if command.auto_sync_enabled
                            else None
                        ),
                        last_sync_status="never",
                        created_by_actor=actor,
                        updated_by_actor=actor,
                    )
                )
            except Exception:
                if asset_saved:
                    try:
                        await self._asset_repository.mark_scene_deleted(
                            tenant_id=asset_scope.tenant_id,
                            scope_type=asset_scope.scope_type,
                            owner_user_id=asset_scope.owner_user_id,
                            asset_key=asset_key,
                            updated_by_actor=actor,
                        )
                    except Exception:  # noqa: BLE001
                        pass
                raise
        return {**scene_to_dict(asset), "git": scene_git_config_to_public_dict(config)}

    async def get_config(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.view")
        asset = await self._require_scene(
            session_user,
            scope,
            scene_asset_key,
            permission_code="scenes.view",
        )
        ensure_git_scene(asset)
        return scene_git_config_to_public_dict(await self._require_config(asset))

    async def update_config(
        self,
        command: UpdateGitSceneConfigCommand,
    ) -> dict[str, object]:
        ensure_admin_permission(command.session_user, "scenes.edit")
        requested_daily_time = (
            None
            if command.daily_sync_time is None
            else parse_daily_sync_time(command.daily_sync_time)
        )
        asset = await self._require_scene(
            command.session_user,
            command.scope,
            command.scene_asset_key,
            permission_code="scenes.edit",
        )
        ensure_git_scene(asset)
        current = await self._require_config(asset)
        next_repository_id = current.git_repository_id
        if command.git_repository_id is not None:
            resource = await require_available_git_resource(
                asset.tenant_id,
                command.git_repository_id,
                self._git_repository,
            )
            next_repository_id = resource.id
        next_timezone = (
            current.timezone if command.timezone is None else validate_timezone(command.timezone)
        )
        next_daily_time = (
            current.daily_sync_time or DEFAULT_SCENE_GIT_DAILY_TIME
            if requested_daily_time is None
            else requested_daily_time
        )
        next_auto_enabled = (
            current.auto_sync_enabled
            if command.auto_sync_enabled is None
            else command.auto_sync_enabled
        )
        next_branch = current.branch if command.branch is None else command.branch.strip()
        next_ref = current.ref if command.ref is None else command.ref.strip()
        next_subdir = (
            current.subdir
            if command.subdir is None
            else normalize_optional_relative_path(command.subdir)
        )
        source_changed = (
            next_repository_id != current.git_repository_id
            or next_branch != current.branch
            or next_ref != current.ref
            or next_subdir != current.subdir
        )
        updated = await self._scene_git_repository.save_config(
            current.model_copy(
                update={
                    "git_repository_id": next_repository_id,
                    "branch": next_branch,
                    "ref": next_ref,
                    "subdir": next_subdir,
                    "last_commit_sha": "" if source_changed else current.last_commit_sha,
                    "auto_sync_enabled": next_auto_enabled,
                    "daily_sync_time": next_daily_time,
                    "timezone": next_timezone,
                    "next_sync_at": (
                        next_daily_sync_at(next_daily_time, next_timezone)
                        if next_auto_enabled
                        else None
                    ),
                    "updated_by_actor": AuditActor.admin_user(command.session_user.user.id),
                }
            )
        )
        return scene_git_config_to_public_dict(updated)

    async def request_sync(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.edit")
        storage_scope, asset_scope = await tenant_storage_and_asset_scope(
            scope,
            session_user,
            self._org_repository,
            permission_code="scenes.edit",
        )
        asset = await _require_scene_asset(
            self._asset_repository,
            asset_scope,
            scene_asset_key,
        )
        ensure_git_scene(asset)
        await self._require_config(asset)
        job, _created = await self._job_repository.create_or_get_active_job(
            BackgroundJob(
                job_id=f"job_{new_uuid4_id()}",
                job_type=SCENE_GIT_JOB_TYPE,
                status="queued",
                trigger_type="manual",
                target_type=SCENE_JOB_TARGET_TYPE,
                target_id=scene_asset_key,
                payload={
                    "scope_type": asset_scope.scope_type,
                    "tenant_id": asset_scope.tenant_id,
                    "tenant_storage_key": storage_scope.scope_tenant_storage_key,
                    "owner_user_id": asset_scope.owner_user_id,
                },
                progress=0,
                message="同步任务已创建",
                created_by_actor=AuditActor.admin_user(session_user.user.id),
            )
        )
        if job.status == "queued" and not job.celery_task_id:
            try:
                task_id = await self._dispatcher.enqueue(job.job_id)
                if not task_id:
                    raise RuntimeError("Scene Git dispatcher returned an empty task id.")
                await self._job_repository.set_celery_task_id(job.job_id, task_id)
            except Exception as exc:
                await self._job_repository.mark_failed(
                    job.job_id,
                    message="Sync job dispatch failed.",
                    error=str(exc),
                )
                raise
        return await self.get_job(session_user, job.job_id)

    async def get_job(
        self,
        session_user: AdminSessionUser,
        job_id: str,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "scenes.view")
        job = await self._job_repository.get_job(job_id)
        if job is None:
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND,
                "Background job does not exist.",
            )
        await self._require_visible_job(session_user, job)
        return background_job_to_dict(job)

    async def list_jobs(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> list[dict[str, object]]:
        ensure_admin_permission(session_user, "scenes.view")
        asset = await self._require_scene(
            session_user,
            scope,
            scene_asset_key,
            permission_code="scenes.view",
        )
        ensure_git_scene(asset)
        jobs = await self._job_repository.list_jobs_for_target(
            job_type=SCENE_GIT_JOB_TYPE,
            target_type=SCENE_JOB_TARGET_TYPE,
            target_id=scene_asset_key,
        )
        return [background_job_to_dict(job) for job in jobs if _job_matches_scene_asset(job, asset)]

    async def delete_config(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
    ) -> None:
        """Delete the Git configuration after the owning shared Scene is removed."""

        ensure_admin_permission(session_user, "scenes.edit")
        asset = await self._require_scene(
            session_user,
            scope,
            scene_asset_key,
            permission_code="scenes.edit",
        )
        ensure_git_scene(asset)
        await self._scene_git_repository.delete_config(
            tenant_id=asset.tenant_id,
            scope_type=asset.scope_type,
            owner_user_id=asset.owner_user_id,
            scene_asset_key=asset.asset_key,
        )

    async def _require_scene(
        self,
        session_user: AdminSessionUser,
        scope: AdminScopeRef,
        scene_asset_key: str,
        *,
        permission_code: str,
    ) -> WorkspaceSceneAsset:
        _, asset_scope = await tenant_storage_and_asset_scope(
            scope,
            session_user,
            self._org_repository,
            permission_code=permission_code,
        )
        return await _require_scene_asset(
            self._asset_repository,
            asset_scope,
            scene_asset_key,
        )

    async def _require_config(self, asset: WorkspaceSceneAsset) -> WorkspaceSceneGitConfig:
        config = await self._scene_git_repository.get_config(
            tenant_id=asset.tenant_id,
            scope_type=asset.scope_type,
            owner_user_id=asset.owner_user_id,
            scene_asset_key=asset.asset_key,
        )
        if config is None:
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND,
                "Scene Git configuration does not exist.",
            )
        return config

    async def _require_visible_job(
        self,
        session_user: AdminSessionUser,
        job: BackgroundJob,
    ) -> None:
        if job.job_type != SCENE_GIT_JOB_TYPE or job.target_type != SCENE_JOB_TARGET_TYPE:
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND,
                "Scene Git sync job does not exist.",
            )
        tenant_id = str(job.payload.get("tenant_id") or "")
        scope_type = str(job.payload.get("scope_type") or "")
        owner_user_id = payload_owner_user_id(job.payload)
        if not tenant_id or scope_type != AdminScopeType.TENANT.value:
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND,
                "Scene Git sync job does not exist.",
            )
        asset = await self._asset_repository.get_scene(
            tenant_id=tenant_id,
            scope_type=scope_type,
            owner_user_id=owner_user_id,
            asset_key=job.target_id,
        )
        if asset is None or asset.source != SCENE_GIT_SOURCE:
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND,
                "Scene Git sync job does not exist.",
            )
        require_manage_scope(
            session_user,
            AdminScopeRef(
                scope_type=AdminScopeType.TENANT,
                scope_tenant_id=tenant_id,
            ),
            "scenes.view",
        )


async def require_available_git_resource(
    tenant_id: str,
    repository_id: str,
    repository: AdminGitRepository,
) -> ManagedGitRepository:
    resource = await repository.get_repository(repository_id)
    if resource is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Git 仓库资源不存在。")
    if resource.status != "active":
        raise ApplicationError(ApplicationErrorKind.CONFLICT, "Git 仓库资源已停用。")
    entitlement = await repository.get_entitlement_by_scope_repository(
        tenant_id=tenant_id,
        scope_type="tenant",
        organization_unit_id="",
        git_repository_id=repository_id,
    )
    if entitlement is None or entitlement.status != "active":
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            "当前触点未获授权使用该 Git 仓库资源。",
        )
    return resource


async def _require_scene_asset(
    repository: WorkspaceSceneAssetRepository,
    scope: ManagedAssetScope,
    scene_asset_key: str,
) -> WorkspaceSceneAsset:
    asset = await repository.get_scene(
        tenant_id=scope.tenant_id,
        scope_type=scope.scope_type,
        owner_user_id=scope.owner_user_id,
        asset_key=scene_asset_key,
    )
    if asset is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Scene does not exist.")
    return asset


def ensure_git_scene(asset: WorkspaceSceneAsset) -> None:
    if asset.source != SCENE_GIT_SOURCE:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "Scene is not Git-backed.")


def normalize_optional_relative_path(path: str) -> str:
    normalized = str(PurePosixPath(path.replace("\\", "/").strip().strip("/")))
    if normalized in {"", "."}:
        return ""
    if any(part in {"", ".", ".."} for part in PurePosixPath(normalized).parts):
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "Git subdir is invalid.")
    return normalized


def validate_timezone(value: str | None) -> str:
    normalized = (value or DEFAULT_SCENE_GIT_TIMEZONE).strip() or DEFAULT_SCENE_GIT_TIMEZONE
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        if normalized in {"Asia/Shanghai", "Asia/Chongqing", "Asia/Harbin", "PRC"}:
            return DEFAULT_SCENE_GIT_TIMEZONE
        if normalized == "UTC":
            return normalized
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "Timezone is invalid.") from exc
    return normalized


def parse_daily_sync_time(value: str) -> time:
    normalized = (value or "03:00").strip()
    try:
        hour_text, minute_text = normalized.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "daily_sync_time must use HH:MM format.",
        ) from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "daily_sync_time must use HH:MM format.",
        )
    return time(hour=hour, minute=minute)


def next_daily_sync_at(
    daily_sync_time: time,
    timezone: str,
    *,
    after: datetime | None = None,
) -> datetime:
    zone = _timezone_info(validate_timezone(timezone))
    base = after or datetime.now(UTC)
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    local_now = base.astimezone(zone)
    candidate = local_now.replace(
        hour=daily_sync_time.hour,
        minute=daily_sync_time.minute,
        second=daily_sync_time.second,
        microsecond=0,
    )
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


def scene_git_config_to_public_dict(config: WorkspaceSceneGitConfig) -> dict[str, object]:
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


def background_job_to_dict(job: BackgroundJob) -> dict[str, object]:
    return {
        "id": job.id,
        "job_id": job.job_id,
        "job_type": job.job_type,
        "status": job.status,
        "trigger_type": job.trigger_type,
        "target_type": job.target_type,
        "target_id": job.target_id,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "celery_task_id": job.celery_task_id,
        "created_by_actor_type": job.created_by_actor.actor_type.value,
        "created_by_actor_id": job.created_by_actor.actor_id,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def payload_owner_user_id(payload: dict[str, object]) -> str | None:
    value = payload.get("owner_user_id")
    return str(value) if value else None


def _job_matches_scene_asset(job: BackgroundJob, asset: WorkspaceSceneAsset) -> bool:
    return (
        job.job_type == SCENE_GIT_JOB_TYPE
        and job.target_type == SCENE_JOB_TARGET_TYPE
        and job.target_id == asset.asset_key
        and str(job.payload.get("tenant_id") or "") == asset.tenant_id
        and str(job.payload.get("scope_type") or "") == asset.scope_type
        and payload_owner_user_id(job.payload) == asset.owner_user_id
    )


def _timezone_info(timezone: str) -> tzinfo:
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        if timezone == DEFAULT_SCENE_GIT_TIMEZONE:
            return fixed_timezone(timedelta(hours=8))
        if timezone == "UTC":
            return UTC
        raise
