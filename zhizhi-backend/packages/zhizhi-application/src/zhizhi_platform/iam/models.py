"""致知 browser-user, admin-session, and authorization domain models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gewu_core.time import utc_now
from zhizhi_platform.iam.identity import AccessScope, OrganizationUnitRef, ScopeType


class AdminScopeType(StrEnum):
    """Admin authorization scope."""

    TENANT = "tenant"
    ORGANIZATION_UNIT = "organization_unit"


class AdminScopeRef(BaseModel):
    """Normalized scope reference for one admin grant or content target."""

    model_config = ConfigDict(frozen=True)

    scope_type: AdminScopeType
    scope_tenant_id: str = ""
    scope_tenant_storage_key: str = Field(default="", exclude=True)
    scope_organization_unit_id: str = ""
    scope_organization_path: tuple[OrganizationUnitRef, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_scope(self) -> AdminScopeRef:
        """Validate identifiers required by one scope type."""

        if not self.scope_tenant_id:
            raise ValueError("scope_tenant_id is required.")
        if self.scope_type is AdminScopeType.ORGANIZATION_UNIT:
            if not self.scope_organization_unit_id:
                raise ValueError(
                    "scope_organization_unit_id is required for organization_unit scope."
                )
            if self.scope_organization_path:
                if self.scope_organization_path[-1].id != self.scope_organization_unit_id:
                    raise ValueError("scope_organization_path must end at the selected unit.")
        return self

    def to_access_scope(
        self,
        *,
        tenant_name: str = "",
    ) -> AccessScope:
        """Convert an admin scope to a readable VFS owner scope."""

        return AccessScope(
            tenant_id=self.scope_tenant_id,
            tenant_storage_key=self.scope_tenant_storage_key,
            scope_type=ScopeType(self.scope_type.value),
            organization_path=self.scope_organization_path,
            tenant_name=tenant_name,
        )


def scope_contains(grant_scope: AdminScopeRef, target_scope: AdminScopeRef) -> bool:
    """Return whether a granted data scope contains a target data scope."""

    if grant_scope.scope_tenant_id != target_scope.scope_tenant_id:
        return False
    if grant_scope.scope_type is AdminScopeType.TENANT:
        return True
    if target_scope.scope_type is not AdminScopeType.ORGANIZATION_UNIT:
        return False
    return (
        grant_scope.scope_organization_unit_id
        in {unit.id for unit in target_scope.scope_organization_path}
        or target_scope.scope_organization_unit_id == grant_scope.scope_organization_unit_id
    )


def scope_strictly_contains(grant_scope: AdminScopeRef, target_scope: AdminScopeRef) -> bool:
    """Return whether a grant contains but is not identical to a target."""

    return scope_contains(grant_scope, target_scope) and _scope_identity(
        grant_scope
    ) != _scope_identity(target_scope)


def _scope_identity(scope: AdminScopeRef) -> tuple[str, str, str]:
    return (
        scope.scope_type.value,
        scope.scope_tenant_id,
        scope.scope_organization_unit_id,
    )


class AdminUser(BaseModel):
    """Admin account entity."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    username: str = Field(min_length=1)
    normalized_username: str = Field(default="", exclude=True)
    password_hash: str = Field(min_length=1)
    display_name: str = ""
    phone: str | None = None
    email: str | None = None
    status: str = "active"
    is_super: bool = False
    token_version: int = Field(default=0, ge=0, exclude=True)
    last_login_time: datetime | None = None
    created_tenant_id: str | None = None
    created_source: str = "system"
    created_by_admin_user_id: str | None = None
    updated_by_admin_user_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AdminRole(BaseModel):
    """Admin role entity."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = ""
    role_code: str = Field(min_length=1)
    role_name: str = Field(min_length=1)
    description: str = ""
    status: str = "active"
    is_delegable: bool = True
    permission_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AdminRolePage(BaseModel):
    """One SQL-filtered page of 致知 administrator roles."""

    model_config = ConfigDict(frozen=True)

    items: tuple[AdminRole, ...] = Field(default_factory=tuple)
    total: int = Field(ge=0)


class AdminPermission(BaseModel):
    """RBAC permission entity."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    permission_code: str = Field(min_length=1)
    permission_name: str = Field(min_length=1)
    module: str = ""
    description: str = ""
    status: str = "active"


class AdminTenantRole(BaseModel):
    """Role binding for one admin tenant member."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_member_id: str = Field(min_length=1)
    role_id: str = Field(min_length=1)
    role: AdminRole | None = None
    permissions: tuple[AdminPermission, ...] = Field(default_factory=tuple)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def is_active(self) -> bool:
        return self.role is None or self.role.status == "active"


class AdminTenantScope(BaseModel):
    """Data-scope binding for one admin tenant member."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_member_id: str = Field(min_length=1)
    scope: AdminScopeRef
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AdminTenantMember(BaseModel):
    """Admin membership inside one tenant tenant."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    admin_user_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    status: str = "active"
    scope_mode: str = AdminScopeType.TENANT.value
    roles: tuple[AdminTenantRole, ...] = Field(default_factory=tuple)
    scopes: tuple[AdminTenantScope, ...] = Field(default_factory=tuple)
    created_by_admin_user_id: str | None = None
    updated_by_admin_user_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def active_roles(self) -> tuple[AdminTenantRole, ...]:
        return tuple(role for role in self.roles if role.is_active)

    @property
    def granted_scopes(self) -> tuple[AdminScopeRef, ...]:
        return tuple(scope.scope for scope in self.scopes)


class AdminTenantAdminRow(BaseModel):
    """One admin identity joined to its tenant membership."""

    model_config = ConfigDict(frozen=True)

    user: AdminUser
    member: AdminTenantMember


class AdminTenantAdminPage(BaseModel):
    """One SQL-filtered page of tenant administrator rows."""

    model_config = ConfigDict(frozen=True)

    items: tuple[AdminTenantAdminRow, ...] = Field(default_factory=tuple)
    total: int = Field(ge=0)


class ManagedTenant(BaseModel):
    """Tenant row managed from the Admin API."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_code: str = Field(min_length=1)
    normalized_tenant_code: str = Field(default="", exclude=True)
    storage_key: str = Field(default="", exclude=True)
    tenant_name: str = ""
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ManagedTenantPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[ManagedTenant, ...] = Field(default_factory=tuple)
    total: int = Field(ge=0)


class ManagedOrganizationUnit(BaseModel):
    """One arbitrary-depth node in a tenant organization tree."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_id: str = Field(min_length=1)
    parent_id: str | None = None
    external_key: str = Field(min_length=1)
    normalized_external_key: str = Field(default="", exclude=True)
    storage_key: str = Field(default="", exclude=True)
    name: str = ""
    unit_type: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    status: str = "active"
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ManagedOrganizationUnitPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[ManagedOrganizationUnit, ...] = Field(default_factory=tuple)
    total: int = Field(ge=0)


class ScopeCatalogNode(BaseModel):
    """Readable managed scope descriptor."""

    model_config = ConfigDict(frozen=True)

    scope: AdminScopeRef
    label: str = ""
    tenant_code: str = ""
    tenant_name: str = ""
    organization_unit_id: str = ""
    parent_organization_unit_id: str = ""
    external_key: str = ""
    unit_type: str = ""


class AdminNavigationItem(BaseModel):
    """Visible menu item for one login session."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    path: str
    permission_code: str
    permission_codes: tuple[str, ...] = Field(default_factory=tuple)
    super_only: bool = False


class AdminSessionUser(BaseModel):
    """Authenticated admin session payload."""

    model_config = ConfigDict(frozen=True)

    user: AdminUser
    roles: tuple[AdminRole, ...] = Field(default_factory=tuple)
    permissions: tuple[AdminPermission, ...] = Field(default_factory=tuple)
    tenant_members: tuple[AdminTenantMember, ...] = Field(default_factory=tuple)

    @property
    def permission_codes(self) -> tuple[str, ...]:
        codes = [permission.permission_code for permission in self.permissions]
        for member in self.active_tenant_members():
            for role in member.active_roles:
                codes.extend(permission.permission_code for permission in role.permissions)
        return tuple(dict.fromkeys(codes))

    def active_tenant_members(self) -> tuple[AdminTenantMember, ...]:
        return tuple(member for member in self.tenant_members if member.is_active)

    def permissions_for_scope(self, scope: AdminScopeRef) -> tuple[AdminPermission, ...]:
        permissions: dict[str, AdminPermission] = {}
        for member in self.active_tenant_members():
            if not any(scope_contains(granted, scope) for granted in member.granted_scopes):
                continue
            for role in member.active_roles:
                for permission in role.permissions:
                    permissions[permission.id] = permission
        return tuple(permissions.values())

    def permission_codes_for_scope(self, scope: AdminScopeRef) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                permission.permission_code for permission in self.permissions_for_scope(scope)
            )
        )

    @property
    def is_super(self) -> bool:
        return self.user.is_super

    @property
    def manageable_scope_keys(self) -> tuple[tuple[str, str, str], ...]:
        keys: list[tuple[str, str, str]] = []
        for member in self.active_tenant_members():
            keys.extend(
                (
                    scope.scope_type.value,
                    scope.scope_tenant_id,
                    scope.scope_organization_unit_id,
                )
                for scope in member.granted_scopes
            )
        return tuple(dict.fromkeys(keys))
