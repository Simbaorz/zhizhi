"""SQLAlchemy model and repository for 致知 administrative audit logs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from gewu_core.database import TimezoneAwareDateTime, db_now
from gewu_core.ids import new_entity_id
from zhizhi_platform.audit.models import AdminAuditLog
from zhizhi_platform.database import ZhizhiBase


class AdminAuditLogModel(ZhizhiBase):
    __tablename__ = "zhizhi_admin_audit_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    operator_admin_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operator_is_super: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    before_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    after_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    request_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )


class MysqlAdminAuditLogRepository:
    """Append each audit record in an independent database transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def append(self, log: AdminAuditLog) -> AdminAuditLog:
        async with self._sessions() as session:
            row = AdminAuditLogModel(
                operator_admin_user_id=log.operator_admin_user_id,
                operator_is_super=log.operator_is_super,
                action=log.action,
                target_resource_type=log.target_resource_type,
                target_resource_id=log.target_resource_id,
                target_tenant_id=log.target_tenant_id,
                scope_summary=log.scope_summary,
                before_summary=log.before_summary,
                after_summary=log.after_summary,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return AdminAuditLog.model_validate(row)
