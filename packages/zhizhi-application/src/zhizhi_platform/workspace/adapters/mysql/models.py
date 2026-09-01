"""Zhizhi background-job table ownership."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gewu_core.database import TimezoneAwareDateTime, db_now
from gewu_core.ids import new_entity_id
from zhizhi_platform.database import ZhizhiBase


class BackgroundJobModel(ZhizhiBase):
    """Persistent status for one Zhizhi asynchronous job."""

    __tablename__ = "zhizhi_background_job"
    __table_args__ = (
        UniqueConstraint("job_id", name="uk_background_job_id"),
        UniqueConstraint("active_key", name="uk_background_job_active_key"),
        Index(
            "idx_background_job_target",
            "job_type",
            "target_type",
            "target_id",
            "create_time",
        ),
        Index(
            "idx_background_job_active",
            "job_type",
            "target_type",
            "target_id",
            "status",
            "create_time",
        ),
        CheckConstraint(
            "(created_by_actor_type = 'system' AND created_by_actor_id IS NULL) OR "
            "(created_by_actor_type = 'admin_user' AND created_by_actor_id IS NOT NULL)",
            name="ck_background_job_created_actor",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    target_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    active_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    error: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    celery_task_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_by_actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    created_by_actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TimezoneAwareDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TimezoneAwareDateTime(), nullable=True)
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )
