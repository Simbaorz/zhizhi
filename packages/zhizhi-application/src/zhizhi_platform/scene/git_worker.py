"""Worker use cases for executing and scheduling Zhizhi Scene Git synchronization."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from gewu_core import ApplicationError, ApplicationErrorKind, new_uuid4_id, utc_now
from zhizhi_platform.audit import AuditActor
from zhizhi_platform.git import (
    GitCheckoutRequest,
    GitCredentials,
    GitRepositoryClient,
    ManagedGitRepository,
    WorkspaceSceneGitConfig,
    WorkspaceSceneGitRepository,
)
from zhizhi_platform.git.ports import AdminGitRepository, GitCredentialCipher
from zhizhi_platform.iam import AdminScopeRef, AdminScopeType
from zhizhi_platform.iam.ports import AdminOrgReadRepository
from zhizhi_platform.scene.git import (
    DEFAULT_SCENE_GIT_DAILY_TIME,
    SCENE_GIT_JOB_TYPE,
    SCENE_GIT_SOURCE,
    SCENE_JOB_TARGET_TYPE,
    ensure_git_scene,
    next_daily_sync_at,
    payload_owner_user_id,
    require_available_git_resource,
)
from zhizhi_platform.workspace.background_jobs import (
    BackgroundJob,
    BackgroundJobRepository,
)
from zhizhi_platform.workspace.models import (
    ManagedWorkspaceRepository,
    WorkspaceSceneAsset,
    WorkspaceSceneAssetRepository,
)
from zhizhi_platform.workspace.policy import scene_content_path

logger = logging.getLogger(__name__)


class SceneGitWorkerService:
    """Execute and schedule Zhizhi Scene Git synchronization jobs."""

    def __init__(
        self,
        *,
        git_repository: AdminGitRepository,
        git_client: GitRepositoryClient,
        credential_cipher: GitCredentialCipher,
        org_repository: AdminOrgReadRepository,
        workspace_repository: ManagedWorkspaceRepository,
        asset_repository: WorkspaceSceneAssetRepository,
        scene_git_repository: WorkspaceSceneGitRepository,
        job_repository: BackgroundJobRepository,
    ) -> None:
        self._git_repository = git_repository
        self._git_client = git_client
        self._credential_cipher = credential_cipher
        self._org_repository = org_repository
        self._workspace_repository = workspace_repository
        self._asset_repository = asset_repository
        self._scene_git_repository = scene_git_repository
        self._job_repository = job_repository

    async def execute(self, job_id: str) -> None:
        """Execute one queued Scene Git synchronization job."""

        job = await self._job_repository.mark_running(
            job_id,
            message="开始同步 Scene Git 仓库",
        )
        if job is None:
            return
        try:
            payload = job.payload
            tenant_id = str(payload.get("tenant_id") or "")
            tenant_storage_key = str(payload.get("tenant_storage_key") or "")
            scope_type = str(payload.get("scope_type") or "")
            owner_user_id = payload_owner_user_id(payload)
            if not tenant_id or not scope_type:
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Sync job payload is invalid.",
                )
            if not tenant_storage_key:
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Sync job payload is missing tenant_storage_key.",
                )
            asset = await self._asset_repository.get_scene(
                tenant_id=tenant_id,
                scope_type=scope_type,
                owner_user_id=owner_user_id,
                asset_key=job.target_id,
            )
            if asset is None:
                raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Scene does not exist.")
            ensure_git_scene(asset)
            config = await self._require_config(asset)
            git_resource = await require_available_git_resource(
                asset.tenant_id,
                config.git_repository_id,
                self._git_repository,
            )
            commit_sha = await self._sync_snapshot(
                asset,
                config,
                git_resource,
                AdminScopeRef(
                    scope_type=AdminScopeType.TENANT,
                    scope_tenant_id=asset.tenant_id,
                    scope_tenant_storage_key=tenant_storage_key,
                ),
                job.job_id,
            )
            await self._asset_repository.save_scene(
                asset.model_copy(update={"updated_by_actor": job.created_by_actor})
            )
            synced_at = utc_now()
            next_sync_at = (
                next_daily_sync_at(
                    config.daily_sync_time or DEFAULT_SCENE_GIT_DAILY_TIME,
                    config.timezone,
                )
                if config.auto_sync_enabled
                else None
            )
            await self._scene_git_repository.update_sync_result(
                tenant_id=asset.tenant_id,
                scope_type=asset.scope_type,
                owner_user_id=asset.owner_user_id,
                scene_asset_key=asset.asset_key,
                status="succeeded",
                error="",
                commit_sha=commit_sha,
                synced_at=synced_at,
                next_sync_at=next_sync_at,
                updated_by_actor=job.created_by_actor,
            )
            await self._job_repository.mark_succeeded(job_id, message="同步完成")
        except Exception as exc:
            error = str(exc)
            await self._job_repository.mark_failed(job_id, message="同步失败", error=error)
            failed_job = await self._job_repository.get_job(job_id)
            failed_payload = failed_job.payload if failed_job is not None else {}
            tenant_id = str(failed_payload.get("tenant_id") or "")
            scope_type = str(failed_payload.get("scope_type") or "")
            if tenant_id and scope_type:
                await self._scene_git_repository.update_sync_result(
                    tenant_id=tenant_id,
                    scope_type=scope_type,
                    owner_user_id=payload_owner_user_id(failed_payload),
                    scene_asset_key=failed_job.target_id if failed_job is not None else "",
                    status="failed",
                    error=error,
                    updated_by_actor=(
                        failed_job.created_by_actor if failed_job is not None else None
                    ),
                )
            raise

    async def dispatch_due(
        self,
        enqueue: Callable[[str], Awaitable[str]],
        *,
        now: datetime | None = None,
        limit: int = 50,
    ) -> list[str]:
        """Create and publish jobs for due automatic synchronization configs."""

        current_time = now or utc_now()
        dispatched_job_ids: list[str] = []
        configs = await self._scene_git_repository.list_due_auto_sync_configs(
            now=current_time,
            limit=limit,
        )
        for config in configs:
            asset = await self._asset_repository.get_scene(
                tenant_id=config.tenant_id,
                scope_type=config.scope_type,
                owner_user_id=config.owner_user_id,
                asset_key=config.scene_asset_key,
            )
            if asset is None or asset.source != SCENE_GIT_SOURCE:
                continue
            storage_scope = await self._tenant_storage_scope(asset.tenant_id)
            job, _created = await self._job_repository.create_or_get_active_job(
                BackgroundJob(
                    job_id=f"job_{new_uuid4_id()}",
                    job_type=SCENE_GIT_JOB_TYPE,
                    status="queued",
                    trigger_type="schedule",
                    target_type=SCENE_JOB_TARGET_TYPE,
                    target_id=config.scene_asset_key,
                    payload={
                        "scope_type": config.scope_type,
                        "tenant_id": config.tenant_id,
                        "tenant_storage_key": storage_scope.scope_tenant_storage_key,
                        "owner_user_id": config.owner_user_id,
                    },
                    progress=0,
                    message="自动同步任务已创建",
                    created_by_actor=AuditActor.system(),
                )
            )
            if job.status != "queued" or job.celery_task_id:
                continue
            next_sync_at = next_daily_sync_at(
                config.daily_sync_time or DEFAULT_SCENE_GIT_DAILY_TIME,
                config.timezone,
                after=current_time + timedelta(seconds=1),
            )
            await self._scene_git_repository.update_sync_result(
                tenant_id=config.tenant_id,
                scope_type=config.scope_type,
                owner_user_id=config.owner_user_id,
                scene_asset_key=config.scene_asset_key,
                status="queued",
                next_sync_at=next_sync_at,
                updated_by_actor=AuditActor.system(),
            )
            try:
                task_id = await enqueue(job.job_id)
                if not task_id:
                    raise RuntimeError("Scene Git dispatcher returned an empty task id.")
                await self._job_repository.set_celery_task_id(job.job_id, task_id)
            except Exception as exc:
                error = str(exc)
                await self._job_repository.mark_failed(
                    job.job_id,
                    message="Scene Git sync dispatch failed.",
                    error=error,
                )
                await self._scene_git_repository.update_sync_result(
                    tenant_id=config.tenant_id,
                    scope_type=config.scope_type,
                    owner_user_id=config.owner_user_id,
                    scene_asset_key=config.scene_asset_key,
                    status="failed",
                    error=error,
                    next_sync_at=current_time,
                    updated_by_actor=AuditActor.system(),
                )
                logger.error(
                    "Unable to dispatch Scene Git sync job job_id=%s exception_type=%s",
                    job.job_id,
                    type(exc).__name__,
                )
                continue
            dispatched_job_ids.append(job.job_id)
        return dispatched_job_ids

    async def _sync_snapshot(
        self,
        asset: WorkspaceSceneAsset,
        config: WorkspaceSceneGitConfig,
        git_resource: ManagedGitRepository,
        scope: AdminScopeRef,
        job_id: str,
    ) -> str:
        await self._job_repository.update_progress(
            job_id,
            progress=10,
            message="正在检查 Git 提交",
        )
        request = GitCheckoutRequest(
            repo_url=git_resource.repo_url,
            credentials=self._credentials(git_resource),
            default_branch=git_resource.default_branch,
            branch=config.branch,
            ref=config.ref,
            subdir=config.subdir,
            max_content_bytes=self._workspace_repository.max_scene_package_bytes,
        )
        remote_commit_sha = await self._git_client.resolve_commit(request)
        if config.last_commit_sha == remote_commit_sha:
            existing_directory = await self._workspace_repository.resolve_managed_directory_async(
                scope,
                scene_content_path(asset.name),
            )
            if existing_directory is not None:
                await self._job_repository.update_progress(
                    job_id,
                    progress=95,
                    message="远端提交未变化，跳过 Scene 内容替换",
                )
                return remote_commit_sha
        await self._job_repository.update_progress(
            job_id,
            progress=20,
            message="正在拉取 Git 仓库",
        )
        async with self._git_client.checkout_snapshot(request) as snapshot:
            await self._job_repository.update_progress(
                job_id,
                progress=55,
                message="正在解析提交版本",
            )
            await self._job_repository.update_progress(
                job_id,
                progress=85,
                message="正在替换 Scene 目录",
            )
            async with self._workspace_repository.serialize_mutation(scope):
                await self._workspace_repository.replace_directory_from_path_async(
                    scope,
                    scene_content_path(asset.name),
                    snapshot.content_path,
                )
            await self._job_repository.update_progress(
                job_id,
                progress=95,
                message="正在写入同步结果",
            )
            return snapshot.commit_sha

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

    async def _tenant_storage_scope(self, tenant_id: str) -> AdminScopeRef:
        scope = await self._org_repository.hydrate_scope(
            AdminScopeRef(
                scope_type=AdminScopeType.TENANT,
                scope_tenant_id=tenant_id,
            )
        )
        if not scope.scope_tenant_storage_key:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Tenant is not enabled for content storage.",
            )
        return scope

    def _credentials(self, repository: ManagedGitRepository) -> GitCredentials:
        if not repository.credential_ciphertext:
            return GitCredentials(username=repository.username)
        payload = self._credential_cipher.decrypt(repository.credential_ciphertext)
        return GitCredentials(
            username=str(payload.get("username") or repository.username),
            password=str(payload.get("password") or ""),
        )
