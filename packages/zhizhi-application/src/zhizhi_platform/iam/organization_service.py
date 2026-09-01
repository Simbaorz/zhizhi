"""Tenant and arbitrary-depth organization management use cases."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.iam.authorization import (
    ensure_admin_scoped_permission,
    ensure_any_admin_permission,
    ensure_super_admin,
)
from zhizhi_platform.iam.catalog import (
    DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
    project_complete_catalog,
)
from zhizhi_platform.iam.codes import build_storage_key, canonical_stable_code
from zhizhi_platform.iam.models import (
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
    ManagedOrganizationUnit,
    ManagedTenant,
)
from zhizhi_platform.iam.organization_policy import (
    ACTIVE_STATUS,
    DELETED_STATUS,
    INACTIVE_STATUS,
    authorized_tenant_ids,
    paged_org_payload,
    raise_if_organization_referenced,
    require_stable_code,
    require_status,
)
from zhizhi_platform.iam.ports import AdminOrgManageRepository, AdminOrgReadRepository

ORG_READ_PERMISSIONS = ("org.view", "admins.view", "llm.view")
SCOPE_CATALOG_READ_PERMISSIONS = (
    "admins.view",
    "admins.assign_role",
    "org.view",
    "skills.view",
    "scenes.view",
    "scene_git.view",
    "llm.view",
    "data_source.view",
)


class CreateTenantCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_code: str
    tenant_name: str = ""
    status: str = ACTIVE_STATUS


class UpdateTenantCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_name: str | None = None
    status: str | None = None


class CreateOrganizationUnitCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    parent_id: str | None = None
    external_key: str
    name: str = ""
    unit_type: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    status: str = ACTIVE_STATUS
    sort_order: int = 0


class UpdateOrganizationUnitCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    parent_id: str | None = None
    parent_id_set: bool = False
    name: str | None = None
    unit_type: str | None = None
    metadata: dict[str, object] | None = None
    status: str | None = None
    sort_order: int | None = None


class OrganizationAdminService:
    """Manage tenants and organization trees without fixed hierarchy levels."""

    def __init__(
        self,
        read_repository: AdminOrgReadRepository,
        repository: AdminOrgManageRepository | None = None,
    ) -> None:
        self._read_repository = read_repository
        self._repository = repository

    @property
    def repository(self) -> AdminOrgManageRepository:
        if self._repository is None:
            raise RuntimeError("Organization management repository is not configured.")
        return self._repository

    async def scope_catalog(self, session_user: AdminSessionUser) -> list[dict[str, object]]:
        ensure_any_admin_permission(session_user, SCOPE_CATALOG_READ_PERMISSIONS)
        visible_scopes = (
            None
            if session_user.is_super
            else tuple(
                scope
                for member in session_user.active_tenant_members()
                for scope in member.granted_scopes
            )
        )
        nodes = await self._read_repository.list_scope_catalog(
            limit=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES + 1,
            visible_scopes=visible_scopes,
        )
        return project_complete_catalog(
            nodes,
            lambda node: node.model_dump(mode="json"),
            max_entries=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
            capacity_message="Scope catalog exceeds the server limit.",
        )

    async def list_tenants(
        self,
        session_user: AdminSessionUser,
        *,
        page: int | None,
        page_size: int,
        search: str,
        status: str,
    ) -> dict[str, object]:
        ensure_any_admin_permission(session_user, ORG_READ_PERMISSIONS)
        visible_ids = (
            None
            if session_user.is_super
            else authorized_tenant_ids(session_user, ORG_READ_PERMISSIONS)
        )
        if page is not None or search.strip() or status != "all":
            result = await self.repository.list_tenants_page(
                page=page or 1,
                page_size=page_size,
                search=search,
                status=status,
                visible_tenant_ids=visible_ids,
            )
            return paged_org_payload("tenants", result, page=page or 1, page_size=page_size)
        rows = await self.repository.list_tenants(
            limit=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES + 1,
            visible_tenant_ids=visible_ids,
        )
        return {
            "tenants": project_complete_catalog(
                rows,
                lambda row: row.model_dump(mode="json"),
                max_entries=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
                capacity_message="Tenant catalog exceeds the server limit.",
            )
        }

    async def create_tenant(
        self, session_user: AdminSessionUser, command: CreateTenantCommand
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        tenant_code = require_stable_code(command.tenant_code, "Tenant code")
        require_status(command.status)
        current = await self.repository.get_tenant_by_code(tenant_code)
        if current is not None and current.status != DELETED_STATUS:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "Tenant code already exists.")
        if current is None:
            current = ManagedTenant(
                tenant_code=tenant_code,
                normalized_tenant_code=canonical_stable_code(tenant_code),
                storage_key=build_storage_key("tenant", tenant_code),
            )
        saved = await self.repository.save_tenant(
            current.model_copy(
                update={"tenant_name": command.tenant_name, "status": command.status}
            )
        )
        return saved.model_dump(mode="json")

    async def update_tenant(
        self,
        session_user: AdminSessionUser,
        tenant_id: str,
        command: UpdateTenantCommand,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        tenant = await _require_tenant(tenant_id, self.repository)
        if command.status is not None:
            require_status(command.status)
            if command.status == INACTIVE_STATUS and tenant.status != INACTIVE_STATUS:
                await _ensure_tenant_is_empty(tenant_id, self.repository)
        saved = await self.repository.save_tenant(
            tenant.model_copy(
                update={
                    "tenant_name": (
                        command.tenant_name
                        if command.tenant_name is not None
                        else tenant.tenant_name
                    ),
                    "status": command.status if command.status is not None else tenant.status,
                }
            )
        )
        return saved.model_dump(mode="json")

    async def delete_tenant(self, session_user: AdminSessionUser, tenant_id: str) -> None:
        ensure_super_admin(session_user)
        await _require_tenant(tenant_id, self.repository)
        await _ensure_tenant_is_empty(tenant_id, self.repository)
        raise_if_organization_referenced(
            await self.repository.organization_reference_counts(tenant_id=tenant_id),
            "Tenant",
        )
        if not await self.repository.mark_tenant_deleted(tenant_id):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Tenant not found.")

    async def list_organization_units(
        self,
        session_user: AdminSessionUser,
        tenant_id: str,
        *,
        page: int | None,
        page_size: int,
        search: str,
        status: str,
    ) -> dict[str, object]:
        await self._require_tenant_scope(session_user, tenant_id, "org.view")
        if page is not None or search.strip() or status != "all":
            result = await self.repository.list_organization_units_page(
                tenant_id=tenant_id,
                page=page or 1,
                page_size=page_size,
                search=search,
                status=status,
            )
            return paged_org_payload(
                "organization_units", result, page=page or 1, page_size=page_size
            )
        rows = await self.repository.list_organization_units(
            tenant_id=tenant_id,
            limit=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES + 1,
        )
        return {
            "organization_units": project_complete_catalog(
                rows,
                lambda row: row.model_dump(mode="json"),
                max_entries=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
                capacity_message="Organization tree exceeds the server limit.",
            )
        }

    async def create_organization_unit(
        self,
        session_user: AdminSessionUser,
        tenant_id: str,
        command: CreateOrganizationUnitCommand,
    ) -> dict[str, object]:
        await self._require_tenant_scope(session_user, tenant_id, "org.manage")
        external_key = require_stable_code(command.external_key, "Organization external key")
        require_status(command.status)
        if (
            await self.repository.get_organization_unit_by_external_key(tenant_id, external_key)
            is not None
        ):
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT, "Organization external key already exists."
            )
        parent = await self._validate_parent(tenant_id, command.parent_id)
        saved = await self.repository.save_organization_unit(
            ManagedOrganizationUnit(
                tenant_id=tenant_id,
                parent_id=parent.id if parent is not None else None,
                external_key=external_key,
                normalized_external_key=canonical_stable_code(external_key),
                storage_key=build_storage_key("organization-unit", tenant_id, external_key),
                name=command.name,
                unit_type=command.unit_type,
                metadata=command.metadata,
                status=command.status,
                sort_order=command.sort_order,
            )
        )
        return saved.model_dump(mode="json")

    async def update_organization_unit(
        self,
        session_user: AdminSessionUser,
        organization_unit_id: str,
        command: UpdateOrganizationUnitCommand,
    ) -> dict[str, object]:
        unit = await _require_organization_unit(organization_unit_id, self.repository)
        await self._require_tenant_scope(session_user, unit.tenant_id, "org.manage")
        if command.status is not None:
            require_status(command.status)
        parent_id = unit.parent_id
        if command.parent_id_set:
            if command.parent_id == unit.id:
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "An organization unit cannot be its own parent.",
                )
            parent = await self._validate_parent(unit.tenant_id, command.parent_id)
            parent_id = parent.id if parent is not None else None
            if parent_id is not None and await self._would_create_cycle(unit.id, parent_id):
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Organization parent change would create a cycle.",
                )
        saved = await self.repository.save_organization_unit(
            unit.model_copy(
                update={
                    "parent_id": parent_id,
                    "name": command.name if command.name is not None else unit.name,
                    "unit_type": (
                        command.unit_type if command.unit_type is not None else unit.unit_type
                    ),
                    "metadata": command.metadata if command.metadata is not None else unit.metadata,
                    "status": command.status if command.status is not None else unit.status,
                    "sort_order": (
                        command.sort_order if command.sort_order is not None else unit.sort_order
                    ),
                }
            )
        )
        return saved.model_dump(mode="json")

    async def delete_organization_unit(
        self, session_user: AdminSessionUser, organization_unit_id: str
    ) -> None:
        unit = await _require_organization_unit(organization_unit_id, self.repository)
        await self._require_tenant_scope(session_user, unit.tenant_id, "org.manage")
        if await self.repository.has_child_organization_units(
            organization_unit_id, active_only=False
        ):
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Delete child organization units first.",
            )
        raise_if_organization_referenced(
            await self.repository.organization_reference_counts(
                organization_unit_id=organization_unit_id
            ),
            "Organization unit",
        )
        if not await self.repository.mark_organization_unit_deleted(organization_unit_id):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Organization unit not found.")

    async def _require_tenant_scope(
        self, session_user: AdminSessionUser, tenant_id: str, permission: str
    ) -> None:
        if session_user.is_super:
            return
        ensure_admin_scoped_permission(
            session_user,
            permission,
            AdminScopeRef(
                scope_type=AdminScopeType.TENANT,
                scope_tenant_id=tenant_id,
            ),
        )

    async def _validate_parent(
        self, tenant_id: str, parent_id: str | None
    ) -> ManagedOrganizationUnit | None:
        if not parent_id:
            return None
        parent = await _require_organization_unit(parent_id, self.repository)
        if parent.tenant_id != tenant_id:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Parent organization unit belongs to another tenant.",
            )
        if parent.status != ACTIVE_STATUS:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Parent organization unit is inactive.",
            )
        return parent

    async def _would_create_cycle(self, unit_id: str, parent_id: str) -> bool:
        current_id: str | None = parent_id
        visited: set[str] = set()
        while current_id:
            if current_id == unit_id or current_id in visited:
                return True
            visited.add(current_id)
            current = await self.repository.get_organization_unit(current_id)
            current_id = current.parent_id if current is not None else None
        return False


async def _require_tenant(tenant_id: str, repository: AdminOrgManageRepository) -> ManagedTenant:
    tenant = await repository.get_tenant(tenant_id)
    if tenant is None or tenant.status == DELETED_STATUS:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Tenant not found.")
    return tenant


async def _require_organization_unit(
    organization_unit_id: str, repository: AdminOrgManageRepository
) -> ManagedOrganizationUnit:
    unit = await repository.get_organization_unit(organization_unit_id)
    if unit is None or unit.status == DELETED_STATUS:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Organization unit not found.")
    return unit


async def _ensure_tenant_is_empty(tenant_id: str, repository: AdminOrgManageRepository) -> None:
    if await repository.tenant_has_organization_units(tenant_id):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Tenant still contains organization units.",
        )
