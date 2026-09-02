"""Durable global installation state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from gewu_core.database import TimezoneAwareDateTime, db_now
from zhizhi_platform.database import ZhizhiBase


class InstallationModel(ZhizhiBase):
    """The singleton row proving that this deployment completed bootstrap."""

    __tablename__ = "zhizhi_installation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bootstrap_version: Mapped[int] = mapped_column(Integer, nullable=False)
    super_admin_user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("zhizhi_admin_user.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    initialized_at: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(),
        nullable=False,
        default=db_now,
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(),
        nullable=False,
        default=db_now,
        onupdate=db_now,
    )
