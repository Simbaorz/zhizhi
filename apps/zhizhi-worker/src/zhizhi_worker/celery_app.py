"""Celery application wiring for Zhizhi."""

from __future__ import annotations

import asyncio
from importlib import import_module
from typing import Any

from gewu_core.apollo_config import load_settings_once
from gewu_core.config import (
    ApolloBootstrapSettings,
    BootstrapSettings,
    load_bootstrap_settings_as,
    load_settings,
)
from zhizhi_worker.broker import celery_broker_url, celery_transport_options
from zhizhi_worker.settings import (
    ZhizhiWorkerBootstrapSettings,
    ZhizhiWorkerSettings,
)
from zhizhi_worker.tasks.chat_media import cleanup_chat_media_job
from zhizhi_worker.tasks.scene_git import (
    SCENE_GIT_DISPATCH_TASK,
    SCENE_GIT_SYNC_TASK,
    dispatch_due_scene_git_syncs_job,
    sync_scene_git_job,
)

CHAT_MEDIA_CLEANUP_TASK = "zhizhi.chat_media.cleanup"


def create_celery_app(
    *,
    bootstrap: BootstrapSettings | None = None,
    settings: ZhizhiWorkerSettings | None = None,
) -> Any:
    """Create a fully configured Zhizhi Celery application."""

    Celery = import_module("celery").Celery  # noqa
    Queue = import_module("kombu").Queue  # noqa
    resolved_bootstrap = bootstrap or load_bootstrap_settings_as(ZhizhiWorkerBootstrapSettings)
    resolved_settings = settings
    if resolved_settings is None:
        if isinstance(resolved_bootstrap, ApolloBootstrapSettings):
            resolved_settings = asyncio.run(
                load_settings_once(
                    ZhizhiWorkerSettings,
                    resolved_bootstrap,
                    required_paths=("redis.connection",),
                )
            )
        else:
            resolved_settings = load_settings(
                ZhizhiWorkerSettings,
                resolved_bootstrap,
                required_paths=("redis.connection",),
            )
    from zhizhi_worker.runtime import prepare_worker_settings

    prepare_worker_settings(resolved_bootstrap, resolved_settings)
    celery_settings = resolved_settings.celery
    app = Celery(
        "zhizhi",
        broker=celery_broker_url(resolved_settings.redis),
    )
    app.conf.update(
        timezone=resolved_bootstrap.timezone.strip() or "Asia/Shanghai",
        enable_utc=True,
        task_track_started=True,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        worker_concurrency=celery_settings.worker_concurrency,
        worker_prefetch_multiplier=1,
        broker_connection_timeout=celery_settings.publish_timeout_seconds,
        task_queues=(Queue("celery"), Queue(celery_settings.scene_git_queue)),
        task_routes={
            SCENE_GIT_SYNC_TASK: {"queue": celery_settings.scene_git_queue},
            SCENE_GIT_DISPATCH_TASK: {"queue": celery_settings.scene_git_queue},
        },
        task_annotations={
            SCENE_GIT_SYNC_TASK: {
                "soft_time_limit": celery_settings.scene_git_soft_time_limit_seconds,
                "time_limit": celery_settings.scene_git_time_limit_seconds,
            },
            SCENE_GIT_DISPATCH_TASK: {
                "soft_time_limit": celery_settings.scene_git_soft_time_limit_seconds,
                "time_limit": celery_settings.scene_git_time_limit_seconds,
            },
        },
        broker_transport_options=celery_transport_options(
            resolved_settings.redis,
            project_name=resolved_bootstrap.project_name,
            mode=resolved_bootstrap.mode.value,
        ),
        beat_schedule={
            "cleanup-chat-media": {
                "task": CHAT_MEDIA_CLEANUP_TASK,
                "schedule": resolved_settings.media.cleanup_interval_seconds,
            },
            "dispatch-due-scene-git-syncs": {
                "task": SCENE_GIT_DISPATCH_TASK,
                "schedule": celery_settings.scene_git_dispatch_interval_seconds,
            },
        },
    )
    app.task(name=CHAT_MEDIA_CLEANUP_TASK)(cleanup_chat_media_job)
    app.task(name=SCENE_GIT_SYNC_TASK)(sync_scene_git_job)
    app.task(name=SCENE_GIT_DISPATCH_TASK)(dispatch_due_scene_git_syncs_job)
    return app


def _prepare_worker_process(**_kwargs: Any) -> None:
    from zhizhi_worker.runtime import prepare_worker_process_runtime

    prepare_worker_process_runtime()


def _shutdown_worker_process(**_kwargs: Any) -> None:
    from zhizhi_worker.runtime import shutdown_worker_process_runtime

    shutdown_worker_process_runtime()


def _register_worker_process_signals() -> None:
    signals = import_module("celery.signals")

    signals.worker_process_init.connect(
        _prepare_worker_process,
        weak=False,
        dispatch_uid="zhizhi-worker-process-init",
    )
    signals.worker_process_shutdown.connect(
        _shutdown_worker_process,
        weak=False,
        dispatch_uid="zhizhi-worker-process-shutdown",
    )


_register_worker_process_signals()
