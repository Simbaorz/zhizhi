"""Lazy composition root for 致知 background worker resources."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, SkipValidation
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gewu_agent_runtime import AttachmentCleanupService
from gewu_agent_runtime.adapters.mysql import SqlAlchemyRuntimeStore
from gewu_core import (
    ConfiguredJsonSecretCipher,
    WorkerAsyncLoop,
    validate_storage_encryption_configuration,
)
from gewu_core.apollo_config import load_settings_once
from gewu_core.blocking import configure_blocking_task_runners
from gewu_core.config import BootstrapSettings, load_bootstrap_settings_as, load_settings
from gewu_core.database import build_async_engine_kwargs, resolve_async_db_url
from gewu_core.file_tasks import configure_file_task_runners, run_file_task
from gewu_core.logging import configure_logging, shutdown_logging
from gewu_core.observability import (
    FilesystemScanRecorder,
    configure_filesystem_scan_recorder,
)
from gewu_core.runtime_temp import (
    prepare_runtime_temp_subdirs,
    resolve_runtime_temp_root,
    set_runtime_temp_root_provider,
)
from gewu_core.time import utc_now
from zhizhi import MysqlSharedSceneAssetRepository
from zhizhi_platform.adapters import build_zhizhi_chat_media_store
from zhizhi_platform.chat_media import ZhizhiChatMediaStore
from zhizhi_platform.git import (
    ConfiguredGitCredentialCipher,
    RestrictedGitRepositoryClient,
    cleanup_stale_scene_git_workspaces,
)
from zhizhi_platform.git.adapters.mysql import MysqlAdminGitRepository
from zhizhi_platform.iam.adapters.mysql import MysqlAdminOrgReadRepository
from zhizhi_platform.scene import SceneGitWorkerService
from zhizhi_platform.schema import ensure_schema_for_mode
from zhizhi_platform.workspace import (
    FilesystemManagedWorkspaceRepository,
    MysqlBackgroundJobRepository,
    MysqlWorkspaceSceneGitRepository,
    resolve_workspace_storage_root,
)
from zhizhi_platform.workspace.observability import (
    install_zhizhi_filesystem_metrics,
)
from zhizhi_worker.broker import celery_broker_url
from zhizhi_worker.settings import (
    ZhizhiWorkerBootstrapSettings,
    ZhizhiWorkerSettings,
)


class ZhizhiWorkerRuntime(BaseModel):
    """Long-lived resources and handlers owned by one Celery child process."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    bootstrap: BootstrapSettings
    settings: ZhizhiWorkerSettings
    db_engine: SkipValidation[AsyncEngine]
    sessions: SkipValidation[async_sessionmaker[AsyncSession]]
    media_store: SkipValidation[ZhizhiChatMediaStore]
    runtime_store: SkipValidation[SqlAlchemyRuntimeStore]
    attachment_cleanup: SkipValidation[AttachmentCleanupService]
    scene_git_sync_service: SkipValidation[SceneGitWorkerService | None] = None


_runtime: ZhizhiWorkerRuntime | None = None
_runtime_lock: asyncio.Lock | None = None
_prepared_bootstrap: BootstrapSettings | None = None
_prepared_settings: ZhizhiWorkerSettings | None = None
_previous_filesystem_scan_recorder: FilesystemScanRecorder | None = None
_worker_async_loop = WorkerAsyncLoop(thread_name="zhizhi-worker-asyncio")
_SCENE_GIT_STALE_GRACE_SECONDS = 60


def prepare_worker_settings(
    bootstrap: BootstrapSettings,
    settings: ZhizhiWorkerSettings,
) -> None:
    """Store the parent-resolved immutable snapshot for Celery child processes."""

    global _prepared_bootstrap, _prepared_settings
    _prepared_bootstrap = bootstrap
    _prepared_settings = settings


async def _recover_stale_scene_git_jobs(
    repository: MysqlBackgroundJobRepository,
    *,
    time_limit_seconds: int,
) -> int:
    """Release reservations left running after a hard worker stop."""

    stale_before = utc_now() - timedelta(
        seconds=time_limit_seconds + _SCENE_GIT_STALE_GRACE_SECONDS
    )
    return await repository.fail_stale_running_jobs(
        job_type="scene_git_sync",
        stale_before=stale_before,
        message="Scene Git sync stopped before completion.",
        error="Worker execution exceeded its hard time limit or exited unexpectedly.",
    )


def run_worker_coroutine[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Run one synchronous Celery task on the process-owned asyncio loop."""

    return _worker_async_loop.run(coroutine)


def prepare_worker_process_runtime() -> None:
    """Discard event-loop and resource state inherited after a process fork."""

    global _runtime, _runtime_lock, _previous_filesystem_scan_recorder
    _worker_async_loop.reset_after_fork()
    _runtime = None
    _runtime_lock = None
    _previous_filesystem_scan_recorder = None


def shutdown_worker_process_runtime() -> None:
    """Close async resources on their owning loop before the worker exits."""

    try:
        if _worker_async_loop.is_running:
            _worker_async_loop.run(_shutdown_worker_runtime())
    finally:
        _worker_async_loop.shutdown()
        shutdown_logging()


async def get_worker_runtime() -> ZhizhiWorkerRuntime:
    """Return the process-owned Worker runtime, building it once."""

    global _runtime, _runtime_lock
    if _runtime is not None:
        return _runtime
    if _runtime_lock is None:
        _runtime_lock = asyncio.Lock()
    async with _runtime_lock:
        if _runtime is None:
            bootstrap = _prepared_bootstrap or load_bootstrap_settings_as(
                ZhizhiWorkerBootstrapSettings
            )
            settings = _prepared_settings
            if settings is None:
                if isinstance(bootstrap, ZhizhiWorkerBootstrapSettings):
                    settings = await load_settings_once(
                        ZhizhiWorkerSettings,
                        bootstrap,
                        required_paths=("redis.connection",),
                    )
                else:
                    settings = load_settings(
                        ZhizhiWorkerSettings,
                        bootstrap,
                        required_paths=("redis.connection",),
                    )
            _runtime = await _build_worker_runtime(bootstrap, settings)
        return _runtime


async def _build_worker_runtime(
    bootstrap: BootstrapSettings,
    settings: ZhizhiWorkerSettings,
) -> ZhizhiWorkerRuntime:
    """Compose external clients on the event loop that will use them."""

    celery_broker_url(settings.redis)
    if not settings.db.enabled:
        raise RuntimeError("Database is not configured.")
    db_url = resolve_async_db_url(settings.db, bootstrap.project_home)
    if not db_url:
        raise RuntimeError("Database is not configured.")
    validate_storage_encryption_configuration(
        settings.storage_encryption,
        bootstrap.mode.value,
    )

    configure_logging(settings.log)
    configure_blocking_task_runners(settings.blocking_io)
    configure_file_task_runners(settings.blocking_io.filesystem)
    temp_root = resolve_runtime_temp_root(settings.runtime.temp_dir, bootstrap.project_home)
    set_runtime_temp_root_provider(lambda: temp_root)
    prepare_runtime_temp_subdirs(("extracts", "file-mutation-locks", "file-rollback", "scene-git"))
    await run_file_task(
        cleanup_stale_scene_git_workspaces,
        older_than_seconds=settings.celery.scene_git_time_limit_seconds,
        wait_on_cancel=True,
    )
    engine: AsyncEngine | None = None
    media_store: ZhizhiChatMediaStore | None = None
    try:
        engine = create_async_engine(
            db_url,
            **build_async_engine_kwargs(settings.db, use_null_pool=True),
        )
        await ensure_schema_for_mode(engine, bootstrap.mode)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        background_job_repository = MysqlBackgroundJobRepository(sessions)
        await _recover_stale_scene_git_jobs(
            background_job_repository,
            time_limit_seconds=settings.celery.scene_git_time_limit_seconds,
        )
        scene_git_sync_service = None
        if settings.workspace.storage_root.strip():
            workspace_root = resolve_workspace_storage_root(
                settings.workspace.storage_root, bootstrap.project_home
            )
            shared_scene_repository = MysqlSharedSceneAssetRepository(sessions)
            scene_git_sync_service = SceneGitWorkerService(
                git_repository=MysqlAdminGitRepository(sessions),
                git_client=RestrictedGitRepositoryClient(
                    settings.scene_git.command_timeout_seconds,
                    settings.scene_git.max_clone_overhead_bytes,
                ),
                credential_cipher=ConfiguredGitCredentialCipher(settings.storage_encryption.key),
                org_repository=MysqlAdminOrgReadRepository(sessions),
                workspace_repository=FilesystemManagedWorkspaceRepository(
                    storage_root=workspace_root,
                    max_file_bytes=settings.workspace.max_file_bytes,
                    max_skill_package_bytes=settings.workspace.max_skill_package_bytes,
                    max_scene_package_bytes=settings.workspace.max_scene_package_bytes,
                    max_listing_entries=settings.workspace.max_listing_entries,
                ),
                asset_repository=shared_scene_repository,
                scene_git_repository=MysqlWorkspaceSceneGitRepository(
                    sessions,
                    scene_assets=shared_scene_repository,
                ),
                job_repository=background_job_repository,
            )
        media_store = build_zhizhi_chat_media_store(
            settings.media,
            bootstrap.project_home,
        )
        store = SqlAlchemyRuntimeStore(
            sessions,
            protected_payload_cipher=ConfiguredJsonSecretCipher(
                settings.storage_encryption.key,
                setting_name="storage_encryption.key",
            ),
        )
        runtime = ZhizhiWorkerRuntime(
            bootstrap=bootstrap,
            settings=settings,
            db_engine=engine,
            sessions=sessions,
            media_store=media_store,
            runtime_store=store,
            attachment_cleanup=AttachmentCleanupService(
                store=store,
                object_store=media_store,
                pending_ttl_hours=settings.media.pending_attachment_ttl_hours,
            ),
            scene_git_sync_service=scene_git_sync_service,
        )
        global _previous_filesystem_scan_recorder
        _previous_filesystem_scan_recorder = install_zhizhi_filesystem_metrics()
        return runtime
    except BaseException:
        if media_store is not None:
            await media_store.close()
        if engine is not None:
            await engine.dispose()
        set_runtime_temp_root_provider(None)
        raise


async def _shutdown_worker_runtime() -> None:
    """Release every process-owned resource in reverse construction order."""

    global _runtime, _runtime_lock, _previous_filesystem_scan_recorder
    runtime = _runtime
    _runtime = None
    _runtime_lock = None
    previous_recorder = _previous_filesystem_scan_recorder
    _previous_filesystem_scan_recorder = None
    if previous_recorder is not None:
        configure_filesystem_scan_recorder(previous_recorder)
    if runtime is not None:
        await _close_worker_runtime(runtime)


async def _close_worker_runtime(runtime: ZhizhiWorkerRuntime) -> None:
    try:
        await runtime.media_store.close()
    finally:
        try:
            await runtime.db_engine.dispose()
        finally:
            set_runtime_temp_root_provider(None)
