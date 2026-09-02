"""Worker task response contract."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any

import pytest

from gewu_agent_runtime import AttachmentCleanupResult
from zhizhi_worker.tasks import chat_media, scene_git


class _CleanupService:
    async def cleanup(self) -> AttachmentCleanupResult:
        return AttachmentCleanupResult(scanned=3, deleted=2, failed=1)


async def test_cleanup_task_returns_json_compatible_result(monkeypatch) -> None:
    async def get_runtime() -> SimpleNamespace:
        return SimpleNamespace(attachment_cleanup=_CleanupService())

    monkeypatch.setattr(chat_media, "get_worker_runtime", get_runtime)

    assert await chat_media._cleanup_chat_media_job() == {
        "scanned": 3,
        "deleted": 2,
        "failed": 1,
    }


class _SceneGitService:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, job_id: str) -> None:
        self.executed.append(job_id)

    async def dispatch_due(self, enqueue) -> list[str]:
        return [await enqueue("job-2")]


async def test_scene_git_tasks_delegate_to_worker_service(monkeypatch) -> None:
    service = _SceneGitService()
    runtime = SimpleNamespace(
        scene_git_sync_service=service,
        settings=SimpleNamespace(
            celery=SimpleNamespace(
                scene_git_queue="scene-git",
                publish_timeout_seconds=3.0,
            )
        ),
    )

    async def get_runtime() -> SimpleNamespace:
        return runtime

    published: list[tuple[str, str, float]] = []

    async def publish(job_id: str, *, queue: str, timeout_seconds: float) -> str:
        published.append((job_id, queue, timeout_seconds))
        return "task-2"

    monkeypatch.setattr(scene_git, "get_worker_runtime", get_runtime)
    monkeypatch.setattr(scene_git, "publish_scene_git_sync_task", publish)

    await scene_git._sync_scene_git_job("job-1")
    dispatched = await scene_git._dispatch_due_scene_git_syncs_job()

    assert service.executed == ["job-1"]
    assert dispatched == ["task-2"]
    assert published == [("job-2", "scene-git", 3.0)]


def test_sync_task_wrappers_submit_to_process_owned_loop(monkeypatch) -> None:
    submitted: list[Coroutine[Any, Any, object]] = []
    results: list[object] = [None, ["task-2"], {"scanned": 3, "deleted": 2, "failed": 1}]

    def run_worker_coroutine(coroutine: Coroutine[Any, Any, object]) -> object:
        submitted.append(coroutine)
        coroutine.close()
        return results[len(submitted) - 1]

    monkeypatch.setattr(scene_git, "run_worker_coroutine", run_worker_coroutine)
    monkeypatch.setattr(chat_media, "run_worker_coroutine", run_worker_coroutine)

    assert scene_git.sync_scene_git_job("job-1") is None
    assert scene_git.dispatch_due_scene_git_syncs_job() == ["task-2"]
    assert chat_media.cleanup_chat_media_job() == {
        "scanned": 3,
        "deleted": 2,
        "failed": 1,
    }
    assert len(submitted) == 3


async def test_scene_git_publish_uses_external_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    caller_thread = threading.get_ident()
    published: list[tuple[str, tuple[str, ...], str, bool, int]] = []

    class App:
        def send_task(
            self,
            name: str,
            *,
            args: tuple[str, ...],
            queue: str,
            retry: bool,
        ) -> SimpleNamespace:
            published.append((name, args, queue, retry, threading.get_ident()))
            return SimpleNamespace(id="task-1")

    monkeypatch.setattr(
        scene_git,
        "import_module",
        lambda name: SimpleNamespace(current_app=App()),
    )

    task_id = await scene_git.publish_scene_git_sync_task(
        "job-1",
        queue="scene-git",
        timeout_seconds=1.0,
    )

    assert task_id == "task-1"
    assert published == [
        (
            scene_git.SCENE_GIT_SYNC_TASK,
            ("job-1",),
            "scene-git",
            False,
            published[0][4],
        )
    ]
    assert published[0][4] != caller_thread


async def test_scene_git_publish_timeout_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scene_git,
        "import_module",
        lambda name: SimpleNamespace(current_app=SimpleNamespace()),
    )

    async def never_finishes(operation: object) -> None:
        del operation
        await asyncio.Event().wait()

    monkeypatch.setattr(scene_git, "run_external_task", never_finishes)

    with pytest.raises(TimeoutError):
        await scene_git.publish_scene_git_sync_task(
            "job-1",
            queue="scene-git",
            timeout_seconds=0.01,
        )
