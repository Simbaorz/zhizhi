"""MySQL persistence for tenant and organization-unit management."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zhizhi_platform.iam.adapters.mysql.admin_org import (
    _organization_unit,
    _tenant,
)
from zhizhi_platform.iam.adapters.mysql.models import OrganizationUnitModel, TenantModel
from zhizhi_platform.iam.codes import build_storage_key, canonical_stable_code
from zhizhi_platform.iam.models import (
    ManagedOrganizationUnit,
    ManagedOrganizationUnitPage,
    ManagedTenant,
    ManagedTenantPage,
)
from zhizhi_platform.iam.ports import OrganizationReferenceQuery

SessionFactory = Callable[[], AsyncSession]
DELETED_STATUS = "deleted"


class MysqlAdminOrgManageRepository:
    """Persist arbitrary-depth organization trees inside tenant boundaries."""

    def __init__(
        self,
        session_factory: SessionFactory,
        reference_query: OrganizationReferenceQuery,
    ) -> None:
        self._sessions = session_factory
        self._references = reference_query

    async def list_tenants(
        self,
        *,
        limit: int | None = None,
        visible_tenant_ids: Sequence[str] | None = None,
    ) -> Sequence[ManagedTenant]:
        conditions = [TenantModel.status != DELETED_STATUS]
        if visible_tenant_ids is not None:
            conditions.append(TenantModel.id.in_(tuple(visible_tenant_ids)))
        statement = select(TenantModel).where(*conditions).order_by(TenantModel.tenant_code.asc())
        if limit is not None:
            statement = statement.limit(limit)
        async with self._sessions() as session:
            rows = tuple(await session.scalars(statement))
        return tuple(_tenant(row) for row in rows)

    async def list_tenants_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
        visible_tenant_ids: Sequence[str] | None = None,
    ) -> ManagedTenantPage:
        conditions = [TenantModel.status != DELETED_STATUS]
        if visible_tenant_ids is not None:
            conditions.append(TenantModel.id.in_(tuple(visible_tenant_ids)))
        if status != "all":
            conditions.append(TenantModel.status == status)
        if search.strip():
            pattern = _search_pattern(search)
            conditions.append(
                or_(
                    TenantModel.tenant_code.ilike(pattern, escape="\\"),
                    TenantModel.tenant_name.ilike(pattern, escape="\\"),
                )
            )
        async with self._sessions() as session:
            total = int(
                await session.scalar(
                    select(func.count()).select_from(TenantModel).where(*conditions)
                )
                or 0
            )
            rows = tuple(
                await session.scalars(
                    select(TenantModel)
                    .where(*conditions)
                    .order_by(TenantModel.tenant_code.asc())
                    .offset(_page_offset(page, page_size))
                    .limit(page_size)
                )
            )
        return ManagedTenantPage(items=tuple(_tenant(row) for row in rows), total=total)

    async def get_tenant(self, tenant_id: str) -> ManagedTenant | None:
        async with self._sessions() as session:
            row = await session.get(TenantModel, tenant_id)
        return _tenant(row) if row is not None else None

    async def get_tenant_by_code(self, tenant_code: str) -> ManagedTenant | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(TenantModel).where(
                    TenantModel.normalized_tenant_code == canonical_stable_code(tenant_code)
                )
            )
        return _tenant(row) if row is not None else None

    async def save_tenant(self, tenant: ManagedTenant) -> ManagedTenant:
        async with self._sessions() as session:
            row = await session.get(TenantModel, tenant.id) if tenant.id else None
            if row is None:
                row = TenantModel(
                    tenant_code=tenant.tenant_code,
                    normalized_tenant_code=canonical_stable_code(tenant.tenant_code),
                    storage_key=build_storage_key("tenant", tenant.tenant_code),
                )
                session.add(row)
            row.tenant_name = tenant.tenant_name
            row.status = tenant.status
            await session.commit()
            await session.refresh(row)
        return _tenant(row)

    async def mark_tenant_deleted(self, tenant_id: str) -> bool:
        async with self._sessions() as session:
            row = await session.get(TenantModel, tenant_id)
            if row is None or row.status == DELETED_STATUS:
                return False
            row.status = DELETED_STATUS
            await session.commit()
        return True

    async def list_organization_units(
        self,
        *,
        tenant_id: str,
        parent_id: str | None = None,
        limit: int | None = None,
    ) -> Sequence[ManagedOrganizationUnit]:
        conditions = [
            OrganizationUnitModel.tenant_id == tenant_id,
            OrganizationUnitModel.status != DELETED_STATUS,
        ]
        if parent_id is not None:
            conditions.append(OrganizationUnitModel.parent_id == (parent_id or None))
        statement = (
            select(OrganizationUnitModel)
            .where(*conditions)
            .order_by(
                OrganizationUnitModel.sort_order.asc(),
                OrganizationUnitModel.external_key.asc(),
            )
        )
        if limit is not None:
            statement = statement.limit(limit)
        async with self._sessions() as session:
            rows = tuple(await session.scalars(statement))
        return tuple(_organization_unit(row) for row in rows)

    async def list_organization_units_page(
        self,
        *,
        tenant_id: str,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> ManagedOrganizationUnitPage:
        conditions = [
            OrganizationUnitModel.tenant_id == tenant_id,
            OrganizationUnitModel.status != DELETED_STATUS,
        ]
        if status != "all":
            conditions.append(OrganizationUnitModel.status == status)
        if search.strip():
            pattern = _search_pattern(search)
            conditions.append(
                or_(
                    OrganizationUnitModel.external_key.ilike(pattern, escape="\\"),
                    OrganizationUnitModel.name.ilike(pattern, escape="\\"),
                    OrganizationUnitModel.unit_type.ilike(pattern, escape="\\"),
                )
            )
        async with self._sessions() as session:
            total = int(
                await session.scalar(
                    select(func.count()).select_from(OrganizationUnitModel).where(*conditions)
                )
                or 0
            )
            rows = tuple(
                await session.scalars(
                    select(OrganizationUnitModel)
                    .where(*conditions)
                    .order_by(
                        OrganizationUnitModel.sort_order.asc(),
                        OrganizationUnitModel.external_key.asc(),
                    )
                    .offset(_page_offset(page, page_size))
                    .limit(page_size)
                )
            )
        return ManagedOrganizationUnitPage(
            items=tuple(_organization_unit(row) for row in rows), total=total
        )

    async def get_organization_unit(
        self, organization_unit_id: str
    ) -> ManagedOrganizationUnit | None:
        async with self._sessions() as session:
            row = await session.get(OrganizationUnitModel, organization_unit_id)
        return _organization_unit(row) if row is not None else None

    async def get_organization_unit_by_external_key(
        self, tenant_id: str, external_key: str
    ) -> ManagedOrganizationUnit | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(OrganizationUnitModel).where(
                    OrganizationUnitModel.tenant_id == tenant_id,
                    OrganizationUnitModel.normalized_external_key
                    == canonical_stable_code(external_key),
                )
            )
        return _organization_unit(row) if row is not None else None

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

    async def has_child_organization_units(
        self, organization_unit_id: str, *, active_only: bool
    ) -> bool:
        status = (
            OrganizationUnitModel.status == "active"
            if active_only
            else OrganizationUnitModel.status != DELETED_STATUS
        )
        async with self._sessions() as session:
            return bool(
                await session.scalar(
                    select(
                        exists().where(
                            OrganizationUnitModel.parent_id == organization_unit_id,
                            status,
                        )
                    )
                )
            )

    async def save_organization_unit(
        self, unit: ManagedOrganizationUnit
    ) -> ManagedOrganizationUnit:
        async with self._sessions() as session:
            row = await session.get(OrganizationUnitModel, unit.id) if unit.id else None
            if row is None:
                row = OrganizationUnitModel(
                    tenant_id=unit.tenant_id,
                    external_key=unit.external_key,
                    normalized_external_key=canonical_stable_code(unit.external_key),
                    storage_key=build_storage_key(
                        "organization-unit", unit.tenant_id, unit.external_key
                    ),
                )
                session.add(row)
            row.parent_id = unit.parent_id
            row.name = unit.name
            row.unit_type = unit.unit_type
            row.metadata_json = dict(unit.metadata)
            row.status = unit.status
            row.sort_order = unit.sort_order
            await session.commit()
            await session.refresh(row)
        return _organization_unit(row)

    async def mark_organization_unit_deleted(self, organization_unit_id: str) -> bool:
        async with self._sessions() as session:
            row = await session.get(OrganizationUnitModel, organization_unit_id)
            if row is None or row.status == DELETED_STATUS:
                return False
            row.status = DELETED_STATUS
            await session.commit()
        return True

    async def tenant_has_organization_units(self, tenant_id: str) -> bool:
        async with self._sessions() as session:
            return bool(
                await session.scalar(
                    select(
                        exists().where(
                            OrganizationUnitModel.tenant_id == tenant_id,
                            OrganizationUnitModel.status != DELETED_STATUS,
                        )
                    )
                )
            )

    async def organization_reference_counts(
        self, *, tenant_id: str = "", organization_unit_id: str = ""
    ) -> dict[str, int]:
        return await self._references.count_references(
            tenant_id=tenant_id, organization_unit_id=organization_unit_id
        )

    async def organization_unit_removal_reference_counts(
        self,
        tenant_id: str,
        retained_organization_unit_ids: Sequence[str],
    ) -> dict[str, int]:
        return await self._references.count_organization_unit_removal_references(
            tenant_id,
            retained_organization_unit_ids,
        )


def _page_offset(page: int, page_size: int) -> int:
    return (page - 1) * page_size


def _search_pattern(value: str) -> str:
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
