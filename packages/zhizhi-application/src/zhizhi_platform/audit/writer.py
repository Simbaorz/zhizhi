"""Sanitized, best-effort administrative audit writer."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from zhizhi_platform.audit.models import AdminAuditActor, AdminAuditLog
from zhizhi_platform.audit.ports import AdminAuditLogRepository

logger = logging.getLogger(__name__)
REDACTED_AUDIT_VALUE = "***"
UNSUPPORTED_AUDIT_VALUE = "[unsupported]"
SENSITIVE_AUDIT_FIELD_MARKERS = (
    "password",
    "passwd",
    "credential",
    "secret",
    "token",
    "api_key",
    "apikey",
    "app_key",
    "access_key",
    "private_key",
    "signing_key",
    "encryption_key",
    "authorization",
    "cookie",
)


class AdminAuditWriter:
    """Append sanitized audit records without changing business outcomes."""

    def __init__(self, repository: AdminAuditLogRepository) -> None:
        self._repository = repository

    async def write(
        self,
        *,
        actor: AdminAuditActor,
        action: str,
        target_resource_type: str,
        target_resource_id: str,
        target_tenant_id: str | None = None,
        scope_summary: dict[str, object] | None = None,
        before_summary: dict[str, object] | None = None,
        after_summary: dict[str, object] | None = None,
    ) -> None:
        """Try one independent append and log only low-sensitivity identifiers on failure."""

        try:
            await self._repository.append(
                AdminAuditLog(
                    operator_admin_user_id=actor.admin_user_id,
                    operator_is_super=actor.is_super,
                    action=action,
                    target_resource_type=target_resource_type,
                    target_resource_id=target_resource_id,
                    target_tenant_id=target_tenant_id,
                    scope_summary=_json_safe_summary(scope_summary),
                    before_summary=_json_safe_summary(before_summary),
                    after_summary=_json_safe_summary(after_summary),
                )
            )
        except Exception as exc:
            logger.error(
                "Failed to append Admin audit record action=%s resource_type=%s "
                "resource_id=%s exception_type=%s",
                action,
                target_resource_type,
                target_resource_id,
                type(exc).__name__,
            )


def _json_safe_summary(summary: dict[str, object] | None) -> dict[str, object]:
    if not summary:
        return {}
    safe = _json_safe(summary)
    return safe if isinstance(safe, dict) else {"value": safe}


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {
            _json_safe_key(key): (
                REDACTED_AUDIT_VALUE if _is_sensitive_audit_field(key) else _json_safe(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, tuple | list | set | frozenset):
        return [_json_safe(item) for item in value]
    return UNSUPPORTED_AUDIT_VALUE


def _json_safe_key(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, int | float | bool | Decimal):
        return str(value)
    if isinstance(value, Enum):
        return _json_safe_key(value.value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return UNSUPPORTED_AUDIT_VALUE


def _is_sensitive_audit_field(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.casefold()
    return any(marker in normalized for marker in SENSITIVE_AUDIT_FIELD_MARKERS)
