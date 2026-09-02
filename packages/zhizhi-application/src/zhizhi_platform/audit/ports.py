"""Persistence boundary for 致知 administrative audit records."""

from typing import Protocol

from zhizhi_platform.audit.models import AdminAuditLog


class AdminAuditLogRepository(Protocol):
    async def append(self, log: AdminAuditLog) -> AdminAuditLog: ...
