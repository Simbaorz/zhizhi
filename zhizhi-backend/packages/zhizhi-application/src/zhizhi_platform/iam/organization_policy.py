"""Validation, visibility, and response rules for 致知 organization use cases."""

from __future__ import annotations

from collections.abc import Sequence

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.iam.codes import validate_stable_code
from zhizhi_platform.iam.models import (
    AdminSessionUser,
    ManagedOrganizationUnitPage,
    ManagedTenant,
    ManagedTenantPage,
)

ACTIVE_STATUS = "active"
INACTIVE_STATUS = "inactive"
DELETED_STATUS = "deleted"
VALID_STATUSES = {ACTIVE_STATUS, INACTIVE_STATUS}


def paged_org_payload(
    key: str,
    page_result: ManagedTenantPage | ManagedOrganizationUnitPage,
    *,
    page: int,
    page_size: int,
) -> dict[str, object]:
    return {
        key: [row.model_dump(mode="json") for row in page_result.items],
        "pagination": {"page": page, "page_size": page_size, "total": page_result.total},
    }


def raise_if_organization_referenced(references: dict[str, int], label: str) -> None:
    if not references:
        return
    summary = ", ".join(f"{name}={count}" for name, count in sorted(references.items()))
    raise ApplicationError(
        ApplicationErrorKind.INVALID_INPUT,
        f"{label}仍被数据源引用，无法删除或解绑：{summary}",
    )


def authorized_tenant_ids(
    session_user: AdminSessionUser,
    permission_codes: Sequence[str],
) -> tuple[str, ...]:
    allowed = {
        member.tenant_id
        for member in session_user.active_tenant_members()
        if member.granted_scopes
        and any(
            permission.permission_code in permission_codes
            for role in member.active_roles
            for permission in role.permissions
        )
    }
    return tuple(sorted(allowed))


def filter_visible_tenants(
    rows: Sequence[ManagedTenant],
    session_user: AdminSessionUser,
    permission_codes: Sequence[str],
) -> list[ManagedTenant]:
    if session_user.is_super:
        return list(rows)
    allowed = set(authorized_tenant_ids(session_user, permission_codes))
    return [row for row in rows if row.id in allowed]


def require_tenant_membership_permission(
    session_user: AdminSessionUser,
    tenant_id: str,
    permission_codes: Sequence[str],
) -> None:
    if session_user.is_super:
        return
    if any(
        member.tenant_id == tenant_id
        and member.granted_scopes
        and any(
            permission.permission_code in permission_codes
            for role in member.active_roles
            for permission in role.permissions
        )
        for member in session_user.active_tenant_members()
    ):
        return
    raise ApplicationError(
        ApplicationErrorKind.FORBIDDEN,
        "Missing tenant-scoped organization read permission.",
    )


def require_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "状态必须是 active 或 inactive。",
        )


def require_stable_code(value: str, label: str) -> str:
    try:
        return validate_stable_code(value, label)
    except ValueError as exc:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, str(exc)) from exc
