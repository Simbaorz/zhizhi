"""Zhizhi background job domain model and outbound contracts."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from zhizhi_platform.audit import AuditActor


class BackgroundJob(BaseModel):
    """Persistent status for one asynchronous background job."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    job_id: str = Field(min_length=1)
    job_type: str = Field(min_length=1)
    status: str = "queued"
    trigger_type: str = "manual"
    target_type: str = ""
    target_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    progress: int = 0
    message: str = ""
    error: str = ""
    celery_task_id: str = ""
    created_by_actor: AuditActor = Field(default_factory=AuditActor.system)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BackgroundJobRepository(Protocol):
    """Persistence boundary for generic asynchronous jobs."""

    async def create_job(self, job: BackgroundJob) -> BackgroundJob: ...

    async def create_or_get_active_job(
        self,
        job: BackgroundJob,
    ) -> tuple[BackgroundJob, bool]: ...

    async def get_job(self, job_id: str) -> BackgroundJob | None: ...

    async def find_active_job(
        self,
        *,
        job_type: str,
        target_type: str,
        target_id: str,
    ) -> BackgroundJob | None: ...

    async def set_celery_task_id(
        self,
        job_id: str,
        celery_task_id: str,
    ) -> BackgroundJob | None: ...

    async def mark_running(self, job_id: str, *, message: str = "") -> BackgroundJob | None: ...

    async def update_progress(
        self,
        job_id: str,
        *,
        progress: int,
        message: str,
    ) -> BackgroundJob | None: ...

    async def mark_succeeded(
        self,
        job_id: str,
        *,
        progress: int = 100,
        message: str = "",
    ) -> BackgroundJob | None: ...

    async def mark_failed(
        self,
        job_id: str,
        *,
        message: str,
        error: str,
    ) -> BackgroundJob | None: ...

    async def fail_stale_running_jobs(
        self,
        *,
        job_type: str,
        stale_before: datetime,
        message: str,
        error: str,
    ) -> int: ...

    async def list_jobs_for_target(
        self,
        *,
        job_type: str,
        target_type: str,
        target_id: str,
        limit: int = 20,
    ) -> Sequence[BackgroundJob]: ...


class SceneGitSyncDispatcher(Protocol):
    """Dispatch one persisted Scene Git sync job to a worker."""

    async def enqueue(self, job_id: str) -> str: ...
