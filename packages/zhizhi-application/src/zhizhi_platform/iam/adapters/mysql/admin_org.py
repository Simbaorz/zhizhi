"""Organization reads required by administrator authorization."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zhizhi_platform.iam.adapters.mysql.models import OrganizationUnitModel, TenantModel
from zhizhi_platform.iam.identity import OrganizationUnitRef
from zhizhi_platform.iam.models import (
    AdminScopeRef,
    AdminScopeType,
    ManagedOrganizationUnit,
    ManagedTenant,
    ScopeCatalogNode,
)

SessionFactory = Callable[[], AsyncSession]
ACTIVE_STATUS = "active"


class MysqlAdminOrgReadRepository:
    """Hydrate tenant and organization-unit scopes using active parent paths."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    async def get_tenant(self, tenant_id: str) -> ManagedTenant | None:
        async with self._sessions() as session:
            row = await session.get(TenantModel, tenant_id)
        return _tenant(row) if row is not None else None

    async def get_organization_units_by_ids(
        self, organization_unit_ids: Sequence[str]
    ) -> Sequence[ManagedOrganizationUnit]:
        ids = tuple(dict.fromkeys(organization_unit_ids))
        if not ids:
            return ()
        async with self._sessions() as session:
            rows = tuple(
                await session.scalars(
                    select(OrganizationUnitModel)
                    .where(OrganizationUnitModel.id.in_(ids))
                    .order_by(OrganizationUnitModel.id.asc())
                )
            )
        return tuple(_organization_unit(row) for row in rows)

    async def get_organization_unit(
        self, organization_unit_id: str
    ) -> ManagedOrganizationUnit | None:
        rows = await self.get_organization_units_by_ids((organization_unit_id,))
        return rows[0] if rows else None

    async def get_organization_path(
        self, tenant_id: str, organization_unit_id: str
    ) -> tuple[ManagedOrganizationUnit, ...]:
        async with self._sessions() as session:
            rows = tuple(
                await session.scalars(
                    select(OrganizationUnitModel).where(
                        OrganizationUnitModel.tenant_id == tenant_id,
                        OrganizationUnitModel.status == ACTIVE_STATUS,
                    )
                )
            )
        by_id = {row.id: row for row in rows}
        current = by_id.get(organization_unit_id)
        if current is None:
            return ()
        reversed_path: list[OrganizationUnitModel] = []
        visited: set[str] = set()
        while current is not None:
            if current.id in visited:
                return ()
            visited.add(current.id)
            reversed_path.append(current)
            current = by_id.get(current.parent_id) if current.parent_id else None
        return tuple(_organization_unit(row) for row in reversed(reversed_path))

    async def descendant_ids(self, organization_unit_ids: Sequence[str]) -> Sequence[str]:
        roots = tuple(dict.fromkeys(organization_unit_ids))
        if not roots:
            return ()
        async with self._sessions() as session:
            rows = tuple(
                await session.execute(
                    select(OrganizationUnitModel.id, OrganizationUnitModel.parent_id).where(
                        OrganizationUnitModel.status == ACTIVE_STATUS
                    )
                )
            )
        children: dict[str, list[str]] = {}
        for unit_id, parent_id in rows:
            if parent_id:
                children.setdefault(str(parent_id), []).append(str(unit_id))
        result: list[str] = []
        pending = list(roots)
        seen = set(roots)
        while pending:
            parent_id = pending.pop()
            for child_id in children.get(parent_id, []):
                if child_id in seen:
                    continue
                seen.add(child_id)
                result.append(child_id)
                pending.append(child_id)
        return tuple(result)

    async def list_scope_catalog(
        self,
        *,
        limit: int,
        visible_scopes: Sequence[AdminScopeRef] | None = None,
    ) -> Sequence[ScopeCatalogNode]:
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        async with self._sessions() as session:
            tenants = tuple(
                await session.scalars(
                    select(TenantModel)
                    .where(TenantModel.status == ACTIVE_STATUS)
                    .order_by(TenantModel.tenant_code.asc())
                )
            )
            units = tuple(
                await session.scalars(
                    select(OrganizationUnitModel)
                    .where(OrganizationUnitModel.status == ACTIVE_STATUS)
                    .order_by(
                        OrganizationUnitModel.tenant_id.asc(),
                        OrganizationUnitModel.sort_order.asc(),
                        OrganizationUnitModel.external_key.asc(),
                    )
                )
            )
        visible_tenants = None
        visible_units: set[str] | None = None
        if visible_scopes is not None:
            visible_tenants = {scope.scope_tenant_id for scope in visible_scopes}
            tenant_wide = {
                scope.scope_tenant_id
                for scope in visible_scopes
                if scope.scope_type is AdminScopeType.TENANT
            }
            visible_units = {
                unit.id for scope in visible_scopes for unit in scope.scope_organization_path
            } | {
                scope.scope_organization_unit_id
                for scope in visible_scopes
                if scope.scope_organization_unit_id
            }
        else:
            tenant_wide = set()
        nodes: list[ScopeCatalogNode] = []
        units_by_tenant: dict[str, list[OrganizationUnitModel]] = {}
        for unit in units:
            units_by_tenant.setdefault(unit.tenant_id, []).append(unit)
        for tenant in tenants:
            if visible_tenants is not None and tenant.id not in visible_tenants:
                continue
            nodes.append(
                ScopeCatalogNode(
                    scope=AdminScopeRef(
                        scope_type=AdminScopeType.TENANT,
                        scope_tenant_id=tenant.id,
                        scope_tenant_storage_key=tenant.storage_key,
                    ),
                    label=tenant.tenant_name or tenant.tenant_code,
                    tenant_code=tenant.tenant_code,
                    tenant_name=tenant.tenant_name,
                )
            )
            tenant_units = units_by_tenant.get(tenant.id, [])
            by_id = {unit.id: unit for unit in tenant_units}
            for unit in tenant_units:
                if (
                    visible_units is not None
                    and tenant.id not in tenant_wide
                    and unit.id not in visible_units
                ):
                    continue
                path = _row_path(unit, by_id)
                if not path:
                    continue
                nodes.append(
                    ScopeCatalogNode(
                        scope=AdminScopeRef(
                            scope_type=AdminScopeType.ORGANIZATION_UNIT,
                            scope_tenant_id=tenant.id,
                            scope_tenant_storage_key=tenant.storage_key,
                            scope_organization_unit_id=unit.id,
                            scope_organization_path=tuple(_unit_ref(item) for item in path),
                        ),
                        label=unit.name or unit.external_key,
                        tenant_code=tenant.tenant_code,
                        tenant_name=tenant.tenant_name,
                        organization_unit_id=unit.id,
                        parent_organization_unit_id=unit.parent_id or "",
                        external_key=unit.external_key,
                        unit_type=unit.unit_type,
                    )
                )
                if len(nodes) >= limit:
                    return tuple(nodes)
        return tuple(nodes[:limit])

    async def hydrate_scope(self, scope: AdminScopeRef) -> AdminScopeRef:
        tenant = await self.get_tenant(scope.scope_tenant_id)
        if tenant is None or tenant.status != ACTIVE_STATUS:
            return scope
        updates: dict[str, object] = {
            "scope_tenant_storage_key": tenant.storage_key,
        }
        if scope.scope_type is AdminScopeType.TENANT:
            return scope.model_copy(update=updates)
        path = await self.get_organization_path(
            scope.scope_tenant_id, scope.scope_organization_unit_id
        )
        if not path:
            return scope.model_copy(update=updates)
        updates["scope_organization_path"] = tuple(
            OrganizationUnitRef(
                id=unit.id,
                external_key=unit.external_key,
                name=unit.name,
                unit_type=unit.unit_type,
                storage_key=unit.storage_key,
            )
            for unit in path
        )
        return scope.model_copy(update=updates)


def _row_path(
    unit: OrganizationUnitModel,
    by_id: dict[str, OrganizationUnitModel],
) -> tuple[OrganizationUnitModel, ...]:
    reversed_path: list[OrganizationUnitModel] = []
    visited: set[str] = set()
    current: OrganizationUnitModel | None = unit
    while current is not None:
        if current.id in visited:
            return ()
        visited.add(current.id)
        reversed_path.append(current)
        current = by_id.get(current.parent_id) if current.parent_id else None
    return tuple(reversed(reversed_path))


def _unit_ref(row: OrganizationUnitModel) -> OrganizationUnitRef:
    return OrganizationUnitRef(
        id=row.id,
        external_key=row.external_key,
        name=row.name,
        unit_type=row.unit_type,
        storage_key=row.storage_key,
    )


def _tenant(row: TenantModel) -> ManagedTenant:
    return ManagedTenant(
        id=row.id,
        tenant_code=row.tenant_code,
        normalized_tenant_code=row.normalized_tenant_code,
        storage_key=row.storage_key,
        tenant_name=row.tenant_name,
        status=row.status,
        created_at=row.create_time,
        updated_at=row.update_time,
    )


def _organization_unit(row: OrganizationUnitModel) -> ManagedOrganizationUnit:
    return ManagedOrganizationUnit(
        id=row.id,
        tenant_id=row.tenant_id,
        parent_id=row.parent_id,
        external_key=row.external_key,
        normalized_external_key=row.normalized_external_key,
        storage_key=row.storage_key,
        name=row.name,
        unit_type=row.unit_type,
        metadata=dict(row.metadata_json),
        status=row.status,
        sort_order=row.sort_order,
        created_at=row.create_time,
        updated_at=row.update_time,
    )
