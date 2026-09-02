"""Worker Celery registration and lifecycle signals."""

from __future__ import annotations

from pathlib import Path

from gewu_core.config import BootstrapSettings
from gewu_core.redis import RedisConnectionSettings, RedisMode
from zhizhi_platform import ChatMediaSettings, ZhizhiRedisSettings
from zhizhi_worker.celery_app import (
    _prepare_worker_process,
    _shutdown_worker_process,
    create_celery_app,
)
from zhizhi_worker.settings import (
    ZhizhiCelerySettings,
    ZhizhiWorkerBootstrapSettings,
    ZhizhiWorkerSettings,
)


def test_celery_app_preserves_capacity_routes_and_cleanup_schedule(tmp_path: Path) -> None:
    bootstrap = ZhizhiWorkerBootstrapSettings(
        PROJECT_NAME="zhizhi",
        PROJECT_HOME=tmp_path,
        INSTANCE_NAMESPACE="test",
        TIMEZONE="UTC",
    )
    settings = ZhizhiWorkerSettings(
        redis=_redis_settings(),
        media=ChatMediaSettings(root="media", cleanup_interval_seconds=123),
        celery=ZhizhiCelerySettings(
            worker_concurrency=3,
            scene_git_queue="scene-git-test",
            scene_git_soft_time_limit_seconds=31,
            scene_git_time_limit_seconds=47,
            publish_timeout_seconds=1.25,
        ),
    )

    app = create_celery_app(bootstrap=bootstrap, settings=settings)

    assert app.conf.broker_url == "redis://redis.internal:6379/0"
    assert app.conf.timezone == "UTC"
    assert app.conf.worker_concurrency == 3
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.broker_connection_timeout == 1.25
    assert {queue.name for queue in app.conf.task_queues} == {"celery", "scene-git-test"}
    assert app.conf.task_routes["zhizhi.scene_git.sync"] == {"queue": "scene-git-test"}
    assert app.conf.task_routes["zhizhi.scene_git.dispatch_due_syncs"] == {
        "queue": "scene-git-test"
    }
    assert app.conf.task_annotations["zhizhi.scene_git.sync"] == {
        "soft_time_limit": 31,
        "time_limit": 47,
    }
    assert app.conf.task_annotations["zhizhi.scene_git.dispatch_due_syncs"] == {
        "soft_time_limit": 31,
        "time_limit": 47,
    }
    assert app.conf.beat_schedule["cleanup-chat-media"] == {
        "task": "zhizhi.chat_media.cleanup",
        "schedule": 123,
    }
    assert app.conf.beat_schedule["dispatch-due-scene-git-syncs"] == {
        "task": "zhizhi.scene_git.dispatch_due_syncs",
        "schedule": 60,
    }
    assert "zhizhi.chat_media.cleanup" in app.tasks
    assert "zhizhi.scene_git.sync" in app.tasks
    assert "zhizhi.scene_git.dispatch_due_syncs" in app.tasks
    assert app.conf.broker_transport_options["global_keyprefix"] == ("zhizhi:test:celery:")


def test_worker_process_callbacks_delegate_runtime_lifecycle(monkeypatch) -> None:
    from zhizhi_worker import runtime as runtime_module

    calls: list[str] = []
    monkeypatch.setattr(
        runtime_module,
        "prepare_worker_process_runtime",
        lambda: calls.append("prepare"),
    )
    monkeypatch.setattr(
        runtime_module,
        "shutdown_worker_process_runtime",
        lambda: calls.append("shutdown"),
    )

    _prepare_worker_process(sender=object())
    _shutdown_worker_process(sender=object(), pid=123)

    assert calls == ["prepare", "shutdown"]


def test_celery_parent_fetches_apollo_once_and_prepares_child_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from zhizhi_worker import celery_app as celery_module
    from zhizhi_worker import runtime as runtime_module

    bootstrap = ZhizhiWorkerBootstrapSettings(
        PROJECT_HOME=tmp_path,
        INSTANCE_NAMESPACE="test",
        CONFIG_SOURCE="apollo",
        APOLLO_BASE_URL="http://apollo.test",
        APOLLO_APP_ID="zhizhi-worker",
        APOLLO_NAMESPACES="application.yml",
    )
    settings = ZhizhiWorkerSettings(redis=_redis_settings())
    loads: list[str] = []
    prepared: list[tuple[BootstrapSettings, ZhizhiWorkerSettings]] = []

    async def load_once(*_args, **_kwargs) -> ZhizhiWorkerSettings:
        loads.append("apollo")
        return settings

    monkeypatch.setattr(celery_module, "load_settings_once", load_once)
    monkeypatch.setattr(
        runtime_module,
        "prepare_worker_settings",
        lambda resolved_bootstrap, resolved_settings: prepared.append(
            (resolved_bootstrap, resolved_settings)
        ),
    )

    create_celery_app(bootstrap=bootstrap)

    assert loads == ["apollo"]
    assert prepared == [(bootstrap, settings)]


def test_worker_process_callbacks_are_registered_once() -> None:
    from celery.signals import worker_process_init, worker_process_shutdown

    init_receivers = [receiver for _key, receiver in worker_process_init.receivers]
    shutdown_receivers = [receiver for _key, receiver in worker_process_shutdown.receivers]

    assert init_receivers.count(_prepare_worker_process) == 1
    assert shutdown_receivers.count(_shutdown_worker_process) == 1


def _redis_settings() -> ZhizhiRedisSettings:
    return ZhizhiRedisSettings(
        enabled=True,
        connection=RedisConnectionSettings(
            mode=RedisMode.STANDALONE,
            host="redis.internal",
        ),
    )
