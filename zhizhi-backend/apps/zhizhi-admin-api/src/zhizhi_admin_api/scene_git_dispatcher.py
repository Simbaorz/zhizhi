"""Celery publication adapter for persisted Scene Git jobs."""

from __future__ import annotations

import asyncio
from importlib import import_module
from typing import Any

from gewu_core.blocking import run_external_task
from gewu_core.redis import RedisSettings, celery_broker_url
from zhizhi_platform.celery import celery_transport_options

SCENE_GIT_SYNC_TASK = "zhizhi.scene_git.sync"


class CelerySceneGitSyncDispatcher:
    """Publish Scene Git job identifiers without blocking the HTTP event loop."""

    def __init__(
        self,
        *,
        redis: RedisSettings,
        project_name: str,
        instance_namespace: str,
        queue: str,
        publish_timeout_seconds: float,
    ) -> None:
        self._redis = redis
        self._project_name = project_name
        self._instance_namespace = instance_namespace
        self._queue = queue
        self._publish_timeout_seconds = publish_timeout_seconds
        self._app: Any | None = None

    async def enqueue(self, job_id: str) -> str:
        """Publish one bounded task and return its Celery identifier."""

        async with asyncio.timeout(self._publish_timeout_seconds):
            task_id = await run_external_task(self._publish, job_id)
        return task_id

    def close(self) -> None:
        """Release any publisher-side broker resources."""

        if self._app is not None:
            self._app.close()
            self._app = None

    def _publish(self, job_id: str) -> str:
        app = self._get_app()
        result = app.send_task(
            SCENE_GIT_SYNC_TASK,
            args=(job_id,),
            queue=self._queue,
            retry=False,
        )
        return str(result.id)

    def _get_app(self) -> Any:
        if self._app is not None:
            return self._app
        Celery = import_module("celery").Celery
        app: Any = Celery(
            "zhizhi-admin-publisher",
            broker=celery_broker_url(self._redis),
        )
        app.conf.update(
            broker_connection_timeout=self._publish_timeout_seconds,
            broker_transport_options=celery_transport_options(
                self._redis,
                project_name=self._project_name,
                instance_namespace=self._instance_namespace,
            ),
        )
        self._app = app
        return app
