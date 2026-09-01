"""SQLAlchemy persistence for Zhizhi background jobs."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from gewu_core.database import db_now
from zhizhi_platform.audit import AuditActor, AuditActorType
from zhizhi_platform.workspace.adapters.mysql.models import BackgroundJobModel
from zhizhi_platform.workspace.background_jobs import BackgroundJob

SessionFactory = Callable[[], AsyncSession]
ACTIVE_JOB_STATUSES = ("queued", "running")


class MysqlBackgroundJobRepository:
    """Persist and atomically transition Zhizhi background jobs."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    async def create_job(self, job: BackgroundJob) -> BackgroundJob:
        async with self._sessions() as session:
            row = self._new_row(job)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._row_to_domain(row)

    async def create_or_get_active_job(
        self,
        job: BackgroundJob,
    ) -> tuple[BackgroundJob, bool]:
        if job.status not in ACTIVE_JOB_STATUSES:
            raise ValueError("Only queued or running jobs can reserve an active target.")
        active_key = self._active_key(job.job_type, job.target_type, job.target_id)
        for _attempt in range(3):
            async with self._sessions() as session:
                row = self._new_row(job, active_key=active_key)
                session.add(row)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    existing = await session.scalar(
                        select(BackgroundJobModel).where(
                            BackgroundJobModel.active_key == active_key
                        )
                    )
                    if existing is not None:
                        return self._row_to_domain(existing), False
                    continue
                await session.refresh(row)
                return self._row_to_domain(row), True
        raise RuntimeError("Unable to reserve an active background job target.")

    async def get_job(self, job_id: str) -> BackgroundJob | None:
        async with self._sessions() as session:
            row = await self._get_row(session, job_id)
            return self._row_to_domain(row) if row is not None else None

    async def find_active_job(
        self,
        *,
        job_type: str,
        target_type: str,
        target_id: str,
    ) -> BackgroundJob | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(BackgroundJobModel)
                .where(
                    BackgroundJobModel.active_key
                    == self._active_key(job_type, target_type, target_id),
                    BackgroundJobModel.status.in_(ACTIVE_JOB_STATUSES),
                )
                .order_by(BackgroundJobModel.create_time.desc())
            )
            return self._row_to_domain(row) if row is not None else None

    async def set_celery_task_id(
        self,
        job_id: str,
        celery_task_id: str,
    ) -> BackgroundJob | None:
        return await self._transition(
            job_id,
            conditions=(
                BackgroundJobModel.status == "queued",
                BackgroundJobModel.celery_task_id == "",
            ),
            values={"celery_task_id": celery_task_id, "update_time": db_now()},
        )

    async def mark_running(
        self,
        job_id: str,
        *,
        message: str = "",
    ) -> BackgroundJob | None:
        now = db_now()
        values: dict[str, Any] = {
            "status": "running",
            "started_at": func.coalesce(BackgroundJobModel.started_at, now),
            "update_time": now,
        }
        if message:
            values["message"] = message
        return await self._transition(
            job_id,
            conditions=(BackgroundJobModel.status == "queued",),
            values=values,
        )

    async def update_progress(
        self,
        job_id: str,
        *,
        progress: int,
        message: str,
    ) -> BackgroundJob | None:
        return await self._transition(
            job_id,
            conditions=(BackgroundJobModel.status == "running",),
            values={
                "progress": _clamp_progress(progress),
                "message": message,
                "update_time": db_now(),
            },
        )

    async def mark_succeeded(
        self,
        job_id: str,
        *,
        progress: int = 100,
        message: str = "",
    ) -> BackgroundJob | None:
        now = db_now()
        return await self._transition(
            job_id,
            conditions=(BackgroundJobModel.status == "running",),
            values={
                "status": "succeeded",
                "active_key": None,
                "progress": _clamp_progress(progress),
                "message": message,
                "error": "",
                "finished_at": now,
                "update_time": now,
            },
        )

    async def mark_failed(
        self,
        job_id: str,
        *,
        message: str,
        error: str,
    ) -> BackgroundJob | None:
        now = db_now()
        return await self._transition(
            job_id,
            conditions=(BackgroundJobModel.status.in_(ACTIVE_JOB_STATUSES),),
            values={
                "status": "failed",
                "active_key": None,
                "message": message,
                "error": error,
                "started_at": func.coalesce(BackgroundJobModel.started_at, now),
                "finished_at": now,
                "update_time": now,
            },
        )

    async def fail_stale_running_jobs(
        self,
        *,
        job_type: str,
        stale_before: datetime,
        message: str,
        error: str,
    ) -> int:
        async with self._sessions() as session:
            now = db_now()
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(BackgroundJobModel)
                    .where(
                        BackgroundJobModel.job_type == job_type,
                        BackgroundJobModel.status == "running",
                        func.coalesce(
                            BackgroundJobModel.started_at,
                            BackgroundJobModel.update_time,
                        )
                        <= stale_before,
                    )
                    .values(
                        status="failed",
                        active_key=None,
                        message=message,
                        error=error,
                        finished_at=now,
                        update_time=now,
                    )
                ),
            )
            await session.commit()
            return result.rowcount

    async def list_jobs_for_target(
        self,
        *,
        job_type: str,
        target_type: str,
        target_id: str,
        limit: int = 20,
    ) -> Sequence[BackgroundJob]:
        async with self._sessions() as session:
            rows = tuple(
                await session.scalars(
                    select(BackgroundJobModel)
                    .where(
                        BackgroundJobModel.job_type == job_type,
                        BackgroundJobModel.target_type == target_type,
                        BackgroundJobModel.target_id == target_id,
                    )
                    .order_by(BackgroundJobModel.create_time.desc())
                    .limit(limit)
                )
            )
        return tuple(self._row_to_domain(row) for row in rows)

    async def _transition(
        self,
        job_id: str,
        *,
        conditions: tuple[ColumnElement[bool], ...],
        values: dict[str, Any],
    ) -> BackgroundJob | None:
        async with self._sessions() as session:
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(BackgroundJobModel)
                    .where(BackgroundJobModel.job_id == job_id, *conditions)
                    .values(**values)
                ),
            )
            if not result.rowcount:
                await session.rollback()
                return None
            await session.commit()
            row = await self._get_row(session, job_id)
            return self._row_to_domain(row) if row is not None else None

    @staticmethod
    async def _get_row(
        session: AsyncSession,
        job_id: str,
    ) -> BackgroundJobModel | None:
        return cast(
            BackgroundJobModel | None,
            await session.scalar(
                select(BackgroundJobModel).where(BackgroundJobModel.job_id == job_id)
            ),
        )

    @staticmethod
    def _new_row(
        job: BackgroundJob,
        *,
        active_key: str | None = None,
    ) -> BackgroundJobModel:
        now = db_now()
        return BackgroundJobModel(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            trigger_type=job.trigger_type,
            target_type=job.target_type,
            target_id=job.target_id,
            active_key=(
                active_key
                if active_key is not None
                else (
                    MysqlBackgroundJobRepository._active_key(
                        job.job_type,
                        job.target_type,
                        job.target_id,
                    )
                    if job.status in ACTIVE_JOB_STATUSES
                    else None
                )
            ),
            payload=dict(job.payload),
            progress=job.progress,
            message=job.message,
            error=job.error,
            celery_task_id=job.celery_task_id,
            created_by_actor_type=job.created_by_actor.actor_type.value,
            created_by_actor_id=job.created_by_actor.actor_id,
            started_at=job.started_at,
            finished_at=job.finished_at,
            create_time=now,
            update_time=now,
        )

    @staticmethod
    def _active_key(job_type: str, target_type: str, target_id: str) -> str:
        identity = "\0".join((job_type, target_type, target_id))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_domain(row: BackgroundJobModel) -> BackgroundJob:
        payload = row.payload if isinstance(row.payload, dict) else {}
        return BackgroundJob(
            id=row.id,
            job_id=row.job_id,
            job_type=row.job_type,
            status=row.status,
            trigger_type=row.trigger_type,
            target_type=row.target_type,
            target_id=row.target_id,
            payload=cast(dict[str, Any], payload),
            progress=row.progress,
            message=row.message,
            error=row.error,
            celery_task_id=row.celery_task_id,
            created_by_actor=AuditActor(
                actor_type=AuditActorType(row.created_by_actor_type),
                actor_id=row.created_by_actor_id,
            ),
            started_at=row.started_at,
            finished_at=row.finished_at,
            created_at=row.create_time,
            updated_at=row.update_time,
        )


def _clamp_progress(progress: int) -> int:
    return max(0, min(100, int(progress)))
