"""Authorization policies shared by 致知 management use cases."""

from collections.abc import Sequence

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.iam.models import (
    AdminScopeRef,
    AdminSessionUser,
    AdminTenantMember,
    scope_strictly_contains,
)

SELF_OPERATION_MESSAGE = "Current account cannot modify its own admin permissions."
PEER_OPERATION_MESSAGE = "Current account can only manage subordinate admin accounts."


def has_admin_permission(session_user: AdminSessionUser, permission_code: str) -> bool:
    """Return whether one administrator holds a global permission."""

    return session_user.is_super or permission_code in session_user.permission_codes


def ensure_admin_permission(
    session_user: AdminSessionUser,
    permission_code: str,
) -> None:
    """Require one global management permission."""

    if not has_admin_permission(session_user, permission_code):
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            f"Missing permission: {permission_code}",
        )


def ensure_any_admin_permission(
    session_user: AdminSessionUser,
    permission_codes: Sequence[str],
) -> None:
    """Require at least one permission from a set of candidates."""

    if session_user.is_super or any(
        code in session_user.permission_codes for code in permission_codes
    ):
        return
    raise ApplicationError(
        ApplicationErrorKind.FORBIDDEN,
        f"Missing permission: one of {', '.join(permission_codes)}",
    )


def has_admin_scoped_permission(
    session_user: AdminSessionUser,
    permission_code: str,
    scope: AdminScopeRef,
) -> bool:
    """Return whether an administrator holds a permission in one target scope."""

    return session_user.is_super or permission_code in session_user.permission_codes_for_scope(
        scope
    )


def has_admin_parent_scoped_permission(
    session_user: AdminSessionUser,
    permission_code: str,
    scope: AdminScopeRef,
) -> bool:
    """Return whether a permission is granted by a strict parent of one scope."""

    if session_user.is_super:
        return True
    return any(
        permission.permission_code == permission_code and permission.status == "active"
        for member in session_user.active_tenant_members()
        if any(
            scope_strictly_contains(granted_scope, scope) for granted_scope in member.granted_scopes
        )
        for role in member.active_roles
        for permission in role.permissions
    )


def permission_view_scopes(
    session_user: AdminSessionUser,
    permission_code: str,
) -> tuple[AdminScopeRef, ...] | None:
    """Return granted scopes carrying a permission, or none for super admins."""

    if session_user.is_super:
        return None
    scopes: dict[tuple[str, str, str], AdminScopeRef] = {}
    for member in session_user.active_tenant_members():
        if not any(
            permission.permission_code == permission_code
            for role in member.active_roles
            for permission in role.permissions
        ):
            continue
        for granted_scope in member.granted_scopes:
            scopes[
                (
                    granted_scope.scope_type.value,
                    granted_scope.scope_tenant_id,
                    granted_scope.scope_organization_unit_id,
                )
            ] = granted_scope
    return tuple(scopes.values())


def ensure_admin_scoped_permission(
    session_user: AdminSessionUser,
    permission_code: str,
    scope: AdminScopeRef,
) -> None:
    """Require one management permission in one target scope."""

    if not has_admin_scoped_permission(session_user, permission_code, scope):
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            f"Missing scoped permission: {permission_code}",
        )


def ensure_super_admin(session_user: AdminSessionUser) -> None:
    """Require the authenticated administrator to be the super administrator."""

    if not session_user.is_super:
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            "Super admin privileges are required.",
        )


def ensure_can_manage_admin_member(
    *,
    session_user: AdminSessionUser,
    target_admin_user_id: str,
    target_member: AdminTenantMember | None = None,
    requested_scopes: Sequence[AdminScopeRef] = (),
) -> None:
    """Require the target account and scopes to be strict subordinates."""

    if target_admin_user_id == session_user.user.id:
        raise ApplicationError(ApplicationErrorKind.FORBIDDEN, SELF_OPERATION_MESSAGE)
    if session_user.is_super:
        return
    if target_member is not None and target_member.granted_scopes:
        _ensure_scopes_are_strict_subordinates(session_user, target_member.granted_scopes)
    if requested_scopes:
        _ensure_scopes_are_strict_subordinates(session_user, requested_scopes)


def _ensure_scopes_are_strict_subordinates(
    session_user: AdminSessionUser,
    target_scopes: Sequence[AdminScopeRef],
) -> None:
    operator_scopes = tuple(
        granted_scope
        for member in session_user.active_tenant_members()
        for granted_scope in member.granted_scopes
    )
    if not operator_scopes:
        raise ApplicationError(ApplicationErrorKind.FORBIDDEN, PEER_OPERATION_MESSAGE)
    for target_scope in target_scopes:
        if not any(scope_strictly_contains(scope, target_scope) for scope in operator_scopes):
            raise ApplicationError(ApplicationErrorKind.FORBIDDEN, PEER_OPERATION_MESSAGE)
