"""Celery task for Runtime attachment lifecycle cleanup."""

from __future__ import annotations

from zhizhi_worker.runtime import get_worker_runtime, run_worker_coroutine


def cleanup_chat_media_job() -> dict[str, int]:
    """Delete one bounded batch of expired chat attachment objects."""

    return run_worker_coroutine(_cleanup_chat_media_job())


async def _cleanup_chat_media_job() -> dict[str, int]:
    runtime = await get_worker_runtime()
    result = await runtime.attachment_cleanup.cleanup()
    return result.model_dump(mode="json")
