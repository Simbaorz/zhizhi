"""Persistence boundary for Zhizhi administrative audit records."""

from typing import Protocol

from zhizhi_platform.audit.models import AdminAuditLog


class AdminAuditLogRepository(Protocol):
    async def append(self, log: AdminAuditLog) -> AdminAuditLog: ...
