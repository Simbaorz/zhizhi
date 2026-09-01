"""Celery tasks for Zhizhi Scene Git synchronization."""

from __future__ import annotations

import asyncio
from importlib import import_module
from typing import Any

from gewu_core.blocking import run_external_task
from zhizhi_worker.runtime import get_worker_runtime, run_worker_coroutine

SCENE_GIT_SYNC_TASK = "zhizhi.scene_git.sync"
SCENE_GIT_DISPATCH_TASK = "zhizhi.scene_git.dispatch_due_syncs"


def sync_scene_git_job(job_id: str) -> None:
    """Execute one persisted Scene Git synchronization job."""

    run_worker_coroutine(_sync_scene_git_job(job_id))


def dispatch_due_scene_git_syncs_job() -> list[str]:
    """Dispatch all currently due automatic Scene Git jobs."""

    return run_worker_coroutine(_dispatch_due_scene_git_syncs_job())


async def _sync_scene_git_job(job_id: str) -> None:
    runtime = await get_worker_runtime()
    service = runtime.scene_git_sync_service
    if service is None:
        raise RuntimeError("Scene Git worker service is not configured.")
    await service.execute(job_id)


async def _dispatch_due_scene_git_syncs_job() -> list[str]:
    runtime = await get_worker_runtime()
    service = runtime.scene_git_sync_service
    if service is None:
        raise RuntimeError("Scene Git worker service is not configured.")

    async def enqueue(job_id: str) -> str:
        return await publish_scene_git_sync_task(
            job_id,
            queue=runtime.settings.celery.scene_git_queue,
            timeout_seconds=runtime.settings.celery.publish_timeout_seconds,
        )

    return await service.dispatch_due(enqueue)


async def publish_scene_git_sync_task(
    job_id: str,
    *,
    queue: str,
    timeout_seconds: float,
) -> str:
    """Publish one worker task through Celery's current configured application."""

    current_app: Any = import_module("celery").current_app

    def publish() -> str:
        result = current_app.send_task(
            SCENE_GIT_SYNC_TASK,
            args=(job_id,),
            queue=queue,
            retry=False,
        )
        return str(result.id)

    async with asyncio.timeout(timeout_seconds):
        return await run_external_task(publish)
