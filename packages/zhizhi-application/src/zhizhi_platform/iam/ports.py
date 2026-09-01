"""Persistence and security boundaries required by Zhizhi IAM use cases."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from zhizhi_platform.iam.models import (
    AdminPermission,
    AdminRole,
    AdminRolePage,
    AdminScopeRef,
    AdminSessionUser,
    AdminTenantAdminPage,
    AdminTenantMember,
    AdminTenantScope,
    AdminUser,
    ManagedOrganizationUnit,
    ManagedOrganizationUnitPage,
    ManagedTenant,
    ManagedTenantPage,
    ScopeCatalogNode,
)


class OrganizationDirectoryEntry(BaseModel):
    """Stable organization-unit reference published across packages."""

    model_config = ConfigDict(frozen=True)

    id: str
    tenant_id: str
    external_key: str
    name: str
    unit_type: str = ""
    parent_id: str = ""
    status: str


class OrganizationDirectory(Protocol):
    """Read-only arbitrary-depth organization queries shared across packages."""

    async def descendant_ids(self, organization_unit_ids: Sequence[str]) -> Sequence[str]: ...

    async def search_organization_unit_ids(
        self,
        keyword: str,
        *,
        include_descendants: bool = False,
    ) -> Sequence[str]: ...

    async def list_active_by_external_keys(
        self, tenant_id: str, external_keys: Sequence[str]
    ) -> Sequence[OrganizationDirectoryEntry]: ...


class AdminUserRepository(Protocol):
    async def get_by_id(self, user_id: str) -> AdminUser | None: ...

    async def get_by_username(self, username: str) -> AdminUser | None: ...

    async def get_by_phone(self, phone: str) -> AdminUser | None: ...

    async def get_by_email(self, email: str) -> AdminUser | None: ...

    async def get_super_admin(self) -> AdminUser | None: ...

    async def list_users(self) -> Sequence[AdminUser]: ...

    async def save(self, user: AdminUser) -> AdminUser: ...

    async def touch_last_login(self, user_id: str) -> None: ...


class AdminRoleRepository(Protocol):
    async def list_roles_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> AdminRolePage: ...

    async def list_active_roles(
        self,
        *,
        limit: int,
        delegable_only: bool,
    ) -> Sequence[AdminRole]: ...

    async def get_role(self, role_id: str) -> AdminRole | None: ...

    async def get_role_by_code(self, role_code: str) -> AdminRole | None: ...

    async def save_role(self, role: AdminRole) -> AdminRole: ...

    async def delete_role(self, role_id: str) -> None: ...

    async def list_permissions(
        self,
        *,
        limit: int | None = None,
    ) -> Sequence[AdminPermission]: ...

    async def get_permissions_by_ids(
        self,
        permission_ids: Sequence[str],
    ) -> Sequence[AdminPermission]: ...

    async def list_role_permissions(
        self,
        role_id: str,
        *,
        limit: int | None = None,
    ) -> Sequence[AdminPermission]: ...

    async def role_has_active_permission_outside(
        self,
        role_id: str,
        permission_codes: Sequence[str],
    ) -> bool: ...

    async def replace_role_permissions(
        self,
        role_id: str,
        permission_ids: Sequence[str],
    ) -> None: ...


class AdminTenantMemberRepository(Protocol):
    async def list_by_principal(
        self,
        admin_user_id: str,
        *,
        active_only: bool = True,
        limit: int | None = None,
    ) -> Sequence[AdminTenantMember]: ...

    async def list_admins_page(
        self,
        tenant_id: str,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> AdminTenantAdminPage: ...

    async def get(self, member_id: str) -> AdminTenantMember | None: ...

    async def get_by_admin_and_tenant(
        self,
        admin_user_id: str,
        tenant_id: str,
    ) -> AdminTenantMember | None: ...

    async def has_membership_outside_tenant(
        self,
        admin_user_id: str,
        tenant_id: str,
    ) -> bool: ...

    async def save_member(self, member: AdminTenantMember) -> AdminTenantMember: ...

    async def create_identity_and_member(
        self,
        user: AdminUser,
        member: AdminTenantMember,
    ) -> tuple[AdminUser, AdminTenantMember]: ...

    async def replace_authorization(
        self,
        member: AdminTenantMember,
        role_ids: Sequence[str],
        scopes: Sequence[AdminTenantScope],
    ) -> AdminTenantMember: ...


class AdminOrgReadRepository(Protocol):
    async def list_scope_catalog(
        self,
        *,
        limit: int,
        visible_scopes: Sequence[AdminScopeRef] | None = None,
    ) -> Sequence[ScopeCatalogNode]: ...

    async def hydrate_scope(self, scope: AdminScopeRef) -> AdminScopeRef: ...


class OrganizationReferenceQuery(Protocol):
    """Cross-package reference counts used before destructive organization changes."""

    async def count_references(
        self,
        *,
        tenant_id: str = "",
        organization_unit_id: str = "",
    ) -> dict[str, int]: ...

    async def count_organization_unit_removal_references(
        self,
        tenant_id: str,
        retained_organization_unit_ids: Sequence[str],
    ) -> dict[str, int]: ...


class AdminOrgManageRepository(Protocol):
    """Organization mutation and management-query persistence boundary."""

    async def list_tenants(
        self,
        *,
        limit: int | None = None,
        visible_tenant_ids: Sequence[str] | None = None,
    ) -> Sequence[ManagedTenant]: ...

    async def list_tenants_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
        visible_tenant_ids: Sequence[str] | None = None,
    ) -> ManagedTenantPage: ...

    async def get_tenant(self, tenant_id: str) -> ManagedTenant | None: ...

    async def get_tenant_by_code(self, tenant_code: str) -> ManagedTenant | None: ...

    async def save_tenant(self, tenant: ManagedTenant) -> ManagedTenant: ...

    async def mark_tenant_deleted(self, tenant_id: str) -> bool: ...

    async def list_organization_units(
        self,
        *,
        tenant_id: str,
        parent_id: str | None = None,
        limit: int | None = None,
    ) -> Sequence[ManagedOrganizationUnit]: ...

    async def list_organization_units_page(
        self,
        *,
        tenant_id: str,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> ManagedOrganizationUnitPage: ...

    async def get_organization_unit(
        self, organization_unit_id: str
    ) -> ManagedOrganizationUnit | None: ...

    async def get_organization_unit_by_external_key(
        self, tenant_id: str, external_key: str
    ) -> ManagedOrganizationUnit | None: ...

    async def get_organization_units_by_ids(
        self, organization_unit_ids: Sequence[str]
    ) -> Sequence[ManagedOrganizationUnit]: ...

    async def has_child_organization_units(
        self, organization_unit_id: str, *, active_only: bool
    ) -> bool: ...

    async def save_organization_unit(
        self, unit: ManagedOrganizationUnit
    ) -> ManagedOrganizationUnit: ...

    async def mark_organization_unit_deleted(self, organization_unit_id: str) -> bool: ...

    async def tenant_has_organization_units(self, tenant_id: str) -> bool: ...

    async def organization_reference_counts(
        self,
        *,
        tenant_id: str = "",
        organization_unit_id: str = "",
    ) -> dict[str, int]: ...

    async def organization_unit_removal_reference_counts(
        self,
        tenant_id: str,
        retained_organization_unit_ids: Sequence[str],
    ) -> dict[str, int]: ...


class AdminSessionRepository(Protocol):
    async def load_session_user(self, user: AdminUser) -> AdminSessionUser: ...


class IdentitySecurity(Protocol):
    def hash_password(self, password: str) -> str: ...

    def verify_password(self, password: str, stored_hash: str) -> bool: ...

    async def hash_password_async(self, password: str) -> str: ...

    async def verify_password_async(self, password: str, stored_hash: str) -> bool: ...

    def issue_admin_token(
        self,
        *,
        user_id: str,
        username: str,
        is_super: bool,
        token_version: int = 0,
    ) -> str: ...

    def decode_admin_token(self, token: str) -> dict[str, Any]: ...


class PasswordTransport(Protocol):
    def decrypt(self, encrypted_password: str) -> str: ...

    async def decrypt_async(self, encrypted_password: str) -> str: ...

    def public_key_payload(self) -> dict[str, str]: ...


class LoginThrottleDecision(Protocol):
    @property
    def blocked(self) -> bool: ...

    @property
    def retry_after_seconds(self) -> int: ...


class LoginThrottlePort(Protocol):
    async def check(self, client_ip: str, username: str) -> LoginThrottleDecision: ...

    async def register_failure(self, client_ip: str, username: str) -> None: ...

    async def register_success(self, username: str) -> None: ...
