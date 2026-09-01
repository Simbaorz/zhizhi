"""Zhizhi administrator tenant-member authorization use cases."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.audit import AdminAuditActor, AdminAuditWriter
from zhizhi_platform.iam.authorization import ensure_can_manage_admin_member
from zhizhi_platform.iam.catalog import (
    DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
    project_complete_catalog,
)
from zhizhi_platform.iam.models import (
    AdminRole,
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
    AdminTenantMember,
    AdminTenantRole,
    AdminTenantScope,
)
from zhizhi_platform.iam.ports import (
    AdminOrgReadRepository,
    AdminRoleRepository,
    AdminTenantMemberRepository,
    AdminUserRepository,
)

VALID_MEMBER_STATUSES = {"active", "inactive"}


class ReplaceTenantMemberAuthorizationCommand(BaseModel):
    """Complete authorization state requested for one tenant member."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    admin_user_id: str
    role_ids: tuple[str, ...]
    scopes: tuple[AdminScopeRef, ...]
    status: str


class TenantMemberAdminService:
    """Handle tenant-member authorization and its detailed audit trail."""

    def __init__(
        self,
        *,
        member_repository: AdminTenantMemberRepository,
        user_repository: AdminUserRepository,
        role_repository: AdminRoleRepository,
        org_repository: AdminOrgReadRepository,
        audit_writer: AdminAuditWriter,
    ) -> None:
        self._member_repository = member_repository
        self._user_repository = user_repository
        self._role_repository = role_repository
        self._org_repository = org_repository
        self._audit_writer = audit_writer

    async def list_assignable_roles(
        self,
        session_user: AdminSessionUser,
    ) -> list[dict[str, object]]:
        """Return active roles that the current operator may delegate."""

        return await list_assignable_admin_roles(
            session_user=session_user,
            role_repository=self._role_repository,
        )

    async def replace_authorization(
        self,
        session_user: AdminSessionUser,
        command: ReplaceTenantMemberAuthorizationCommand,
    ) -> dict[str, object]:
        """Replace roles and scopes and then append a best-effort audit record."""

        member = await replace_admin_tenant_member_authorization(
            tenant_id=command.tenant_id,
            admin_user_id=command.admin_user_id,
            role_ids=command.role_ids,
            scopes=command.scopes,
            status=command.status,
            session_user=session_user,
            member_repository=self._member_repository,
            user_repository=self._user_repository,
            role_repository=self._role_repository,
            org_repository=self._org_repository,
        )
        await self._audit_writer.write(
            actor=_admin_audit_actor(session_user),
            action="admin_tenant_member.authorize",
            target_resource_type="zhizhi_admin_tenant_member",
            target_resource_id=str(member["id"]),
            target_tenant_id=command.tenant_id,
            scope_summary={
                "scope_mode": member.get("scope_mode"),
                "scopes": member.get("scopes", []),
            },
            after_summary=member,
        )
        return member

    async def deactivate_member(
        self,
        session_user: AdminSessionUser,
        member_id: str,
    ) -> dict[str, object]:
        """Deactivate one tenant member and then append a best-effort audit record."""

        member = await deactivate_admin_tenant_member(
            member_id=member_id,
            session_user=session_user,
            member_repository=self._member_repository,
        )
        await self._audit_writer.write(
            actor=_admin_audit_actor(session_user),
            action="admin_tenant_member.deactivate",
            target_resource_type="zhizhi_admin_tenant_member",
            target_resource_id=member_id,
            target_tenant_id=str(member.get("tenant_id") or ""),
            scope_summary={
                "scope_mode": member.get("scope_mode"),
                "scopes": member.get("scopes", []),
            },
            after_summary=member,
        )
        return member


async def list_assignable_admin_roles(
    *,
    session_user: AdminSessionUser,
    role_repository: AdminRoleRepository,
) -> list[dict[str, object]]:
    """Return roles the current admin can assign."""

    if not session_user.is_super and "admins.assign_role" not in session_user.permission_codes:
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            "Missing permission: admins.assign_role",
        )
    roles = await role_repository.list_active_roles(
        limit=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES + 1,
        delegable_only=not session_user.is_super,
    )
    return project_complete_catalog(
        roles,
        lambda role: role.model_dump(mode="json"),
        max_entries=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
        capacity_message="Assignable role catalog exceeds the server limit.",
    )


async def replace_admin_tenant_member_authorization(
    *,
    tenant_id: str,
    admin_user_id: str,
    role_ids: Sequence[str],
    scopes: Sequence[AdminScopeRef],
    status: str,
    session_user: AdminSessionUser,
    member_repository: AdminTenantMemberRepository,
    user_repository: AdminUserRepository,
    role_repository: AdminRoleRepository,
    org_repository: AdminOrgReadRepository,
) -> dict[str, object]:
    """Replace roles and data scopes for one bound admin tenant member."""

    _require_member_status(status)
    hydrated_scopes = await _hydrate_and_validate_scopes(
        tenant_id=tenant_id,
        scopes=scopes,
        org_repository=org_repository,
    )
    resolved_scope_mode = _derive_scope_mode(hydrated_scopes)
    for scope in hydrated_scopes:
        _require_scoped_permission(session_user, "admins.assign_role", scope)
    target_user = await user_repository.get_by_id(admin_user_id)
    if target_user is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Admin user does not exist.")
    if target_user.is_super:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Super admin accounts cannot be bound to tenants.",
        )
    existing = await member_repository.get_by_admin_and_tenant(admin_user_id, tenant_id)
    if existing is None:
        raise ApplicationError(
            ApplicationErrorKind.NOT_FOUND,
            "Admin tenant member does not exist.",
        )
    ensure_can_manage_admin_member(
        session_user=session_user,
        target_admin_user_id=admin_user_id,
        target_member=existing,
        requested_scopes=hydrated_scopes,
    )
    await _ensure_assignable_roles(
        role_ids,
        session_user=session_user,
        role_repository=role_repository,
        target_scopes=hydrated_scopes,
    )
    member = await member_repository.replace_authorization(
        existing.model_copy(
            update={
                "status": status,
                "scope_mode": resolved_scope_mode,
                "updated_by_admin_user_id": session_user.user.id,
            }
        ),
        role_ids,
        tuple(
            AdminTenantScope(tenant_member_id=existing.id, scope=scope) for scope in hydrated_scopes
        ),
    )
    return tenant_member_payload(member)


async def deactivate_admin_tenant_member(
    *,
    member_id: str,
    session_user: AdminSessionUser,
    member_repository: AdminTenantMemberRepository,
) -> dict[str, object]:
    """Deactivate one admin tenant member."""

    member = await member_repository.get(member_id)
    if member is None:
        raise ApplicationError(
            ApplicationErrorKind.NOT_FOUND,
            "Admin tenant member does not exist.",
        )
    ensure_can_manage_admin_member(
        session_user=session_user,
        target_admin_user_id=member.admin_user_id,
        target_member=member,
    )
    for scope in _member_operation_scopes(member):
        _require_scoped_permission(session_user, "admins.assign_role", scope)
    saved = await member_repository.save_member(
        member.model_copy(
            update={
                "status": "inactive",
                "updated_by_admin_user_id": session_user.user.id,
            }
        )
    )
    return tenant_member_payload(saved)


async def bind_admin_tenant_member(
    *,
    tenant_id: str,
    admin_user_id: str,
    status: str,
    session_user: AdminSessionUser,
    member_repository: AdminTenantMemberRepository,
    user_repository: AdminUserRepository,
    org_repository: AdminOrgReadRepository,
) -> dict[str, object]:
    """Bind one existing admin identity to a tenant without assigning authorization."""

    _require_member_status(status)
    tenant_scope = await org_repository.hydrate_scope(
        AdminScopeRef(
            scope_type=AdminScopeType.TENANT,
            scope_tenant_id=tenant_id,
        )
    )
    _require_scoped_permission(session_user, "admins.create", tenant_scope)
    target_user = await user_repository.get_by_id(admin_user_id)
    if target_user is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Admin user does not exist.")
    if target_user.is_super:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Super admin accounts cannot be bound to tenants.",
        )
    ensure_can_manage_admin_member(
        session_user=session_user,
        target_admin_user_id=admin_user_id,
    )
    if await member_repository.get_by_admin_and_tenant(admin_user_id, tenant_id) is not None:
        raise ApplicationError(ApplicationErrorKind.CONFLICT, "already_bound")
    member = await member_repository.save_member(
        AdminTenantMember(
            admin_user_id=admin_user_id,
            tenant_id=tenant_id,
            status=status,
            scope_mode=AdminScopeType.TENANT.value,
            created_by_admin_user_id=session_user.user.id,
            updated_by_admin_user_id=session_user.user.id,
        )
    )
    return tenant_member_payload(member)


def tenant_member_payload(member: AdminTenantMember) -> dict[str, object]:
    """Serialize one admin tenant member with the original Zhizhi shape."""

    return {
        "id": member.id,
        "admin_user_id": member.admin_user_id,
        "tenant_id": member.tenant_id,
        "status": member.status,
        "scope_mode": str(member.scope_mode),
        "roles": [_tenant_role_payload(role) for role in member.roles],
        "scopes": [_tenant_scope_payload(scope) for scope in member.scopes],
        "created_by_admin_user_id": member.created_by_admin_user_id,
        "updated_by_admin_user_id": member.updated_by_admin_user_id,
        "created_at": member.created_at,
        "updated_at": member.updated_at,
    }


def _member_operation_scopes(member: AdminTenantMember) -> tuple[AdminScopeRef, ...]:
    if member.granted_scopes:
        return member.granted_scopes
    return (
        AdminScopeRef(
            scope_type=AdminScopeType.TENANT,
            scope_tenant_id=member.tenant_id,
        ),
    )


def _tenant_role_payload(tenant_role: AdminTenantRole) -> dict[str, object]:
    role = tenant_role.role
    return {
        "id": tenant_role.id,
        "role_id": tenant_role.role_id,
        "role_code": role.role_code if role else "",
        "role_name": role.role_name if role else f"role_id={tenant_role.role_id}",
    }


def _tenant_scope_payload(tenant_scope: AdminTenantScope) -> dict[str, object]:
    scope = tenant_scope.scope
    return {
        "id": tenant_scope.id,
        "scope_type": scope.scope_type.value,
        "scope_tenant_id": scope.scope_tenant_id,
        "scope_organization_unit_id": scope.scope_organization_unit_id,
    }


async def _hydrate_and_validate_scopes(
    *,
    tenant_id: str,
    scopes: Sequence[AdminScopeRef],
    org_repository: AdminOrgReadRepository,
) -> tuple[AdminScopeRef, ...]:
    requested = tuple(scopes) or (
        AdminScopeRef(
            scope_type=AdminScopeType.TENANT,
            scope_tenant_id=tenant_id,
        ),
    )
    hydrated = tuple([await org_repository.hydrate_scope(scope) for scope in requested])
    for scope in hydrated:
        if scope.scope_tenant_id != tenant_id:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Scope tenant must match member tenant.",
            )
    return _validate_scope_combination(hydrated)


def _validate_scope_combination(scopes: Sequence[AdminScopeRef]) -> tuple[AdminScopeRef, ...]:
    deduped = tuple({_scope_key(scope): scope for scope in scopes}.values())
    tenant_scopes = [scope for scope in deduped if scope.scope_type is AdminScopeType.TENANT]
    if tenant_scopes:
        if len(deduped) != 1:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Tenant scope cannot be combined with other scopes.",
            )
        return (tenant_scopes[0],)
    organization_scopes = [
        scope for scope in deduped if scope.scope_type in {AdminScopeType.ORGANIZATION_UNIT}
    ]
    if len(organization_scopes) > 1:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "At most one organization-unit scope is allowed.",
        )
    if not deduped:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT, "At least one scope is required."
        )
    return deduped


def _derive_scope_mode(scopes: Sequence[AdminScopeRef]) -> str:
    scope_types = {scope.scope_type for scope in scopes}
    if scope_types == {AdminScopeType.TENANT}:
        return AdminScopeType.TENANT.value
    organization_types = scope_types & {AdminScopeType.ORGANIZATION_UNIT}
    if len(scope_types) == 1 and organization_types:
        return next(iter(organization_types)).value
    return "custom"


def _scope_key(scope: AdminScopeRef) -> tuple[str, str, str]:
    return (
        scope.scope_type.value,
        scope.scope_tenant_id,
        scope.scope_organization_unit_id,
    )


async def _ensure_assignable_roles(
    role_ids: Sequence[str],
    *,
    session_user: AdminSessionUser,
    role_repository: AdminRoleRepository,
    target_scopes: Sequence[AdminScopeRef],
) -> tuple[AdminRole, ...]:
    unique_role_ids = tuple(dict.fromkeys(role_ids))
    if not unique_role_ids:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "At least one role is required.")
    roles: list[AdminRole] = []
    for role_id in unique_role_ids:
        role = await role_repository.get_role(role_id)
        if role is None or role.status != "active":
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND,
                "Role does not exist or is inactive.",
            )
        if not session_user.is_super and not role.is_delegable:
            raise ApplicationError(
                ApplicationErrorKind.FORBIDDEN,
                "Current account cannot assign this role.",
            )
        await _ensure_role_permissions_within_operator_scope(
            role.id,
            session_user=session_user,
            role_repository=role_repository,
            target_scopes=target_scopes,
        )
        roles.append(role)
    return tuple(roles)


async def _ensure_role_permissions_within_operator_scope(
    role_id: str,
    *,
    session_user: AdminSessionUser,
    role_repository: AdminRoleRepository,
    target_scopes: Sequence[AdminScopeRef],
) -> None:
    if session_user.is_super or not target_scopes:
        return
    allowed_permission_codes = set(session_user.permission_codes_for_scope(target_scopes[0]))
    for scope in target_scopes[1:]:
        allowed_permission_codes.intersection_update(session_user.permission_codes_for_scope(scope))
    if await role_repository.role_has_active_permission_outside(
        role_id,
        tuple(allowed_permission_codes),
    ):
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            "Current account cannot assign roles with permissions it does not have.",
        )


def _require_scoped_permission(
    session_user: AdminSessionUser,
    permission_code: str,
    scope: AdminScopeRef,
) -> None:
    if session_user.is_super:
        return
    if permission_code not in session_user.permission_codes_for_scope(scope):
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            f"Missing scoped permission: {permission_code}",
        )


def _require_member_status(status: str) -> None:
    if status not in VALID_MEMBER_STATUSES:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "成员状态必须是 active 或 inactive。",
        )


def _admin_audit_actor(session_user: AdminSessionUser) -> AdminAuditActor:
    return AdminAuditActor(
        admin_user_id=session_user.user.id,
        is_super=session_user.is_super,
    )
