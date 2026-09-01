"""SQLAlchemy persistence for Zhizhi-managed Data Source resources."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import and_, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zhizhi_platform.data_source.adapters.mysql.models import (
    DataSourceSourceBindingModel,
    DataSourceSourceEntitlementModel,
    DataSourceSourceModel,
)
from zhizhi_platform.data_source.domain import (
    ManagedDataSourceSource,
    ManagedDataSourceSourceBinding,
    ManagedDataSourceSourceEntitlement,
)
from zhizhi_platform.data_source.ports import DataSourcePage
from zhizhi_platform.iam import AdminScopeRef, AdminScopeType, OrganizationDirectory

SessionFactory = Callable[[], AsyncSession]
DATA_SOURCE_FIELDS = (
    "source_key",
    "display_name",
    "description",
    "status",
    "api_url",
    "app_id",
    "credentials_ciphertext",
    "credential_status",
    "default_database_key",
    "exec_sources_code",
    "timeout_seconds",
    "default_max_rows",
    "hard_max_rows",
    "allow_databases",
    "log_sql",
)


class MysqlDataSourceAdminRepository:
    """Store and page all Zhizhi Data Source management resources."""

    def __init__(
        self,
        session_factory: SessionFactory,
        organization_directory: OrganizationDirectory,
    ) -> None:
        self._sessions = session_factory
        self._areas = organization_directory

    async def list_sources_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> DataSourcePage:
        model = DataSourceSourceModel
        conditions = []
        if status != "all":
            conditions.append(model.status == status)
        keyword = search.strip()
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            conditions.append(
                or_(
                    model.source_key.ilike(pattern, escape="\\"),
                    model.display_name.ilike(pattern, escape="\\"),
                    model.description.ilike(pattern, escape="\\"),
                    model.api_url.ilike(pattern, escape="\\"),
                    model.app_id.ilike(pattern, escape="\\"),
                    model.default_database_key.ilike(pattern, escape="\\"),
                    model.exec_sources_code.ilike(pattern, escape="\\"),
                )
            )
        async with self._sessions() as session:
            total = int(
                await session.scalar(select(func.count()).select_from(model).where(*conditions))
                or 0
            )
            rows = tuple(
                await session.scalars(
                    select(model)
                    .where(*conditions)
                    .order_by(model.source_key.asc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
        return DataSourcePage(
            items=tuple(_source_from_row(row) for row in rows),
            total=total,
        )

    async def get_source(self, source_id: str) -> ManagedDataSourceSource | None:
        async with self._sessions() as session:
            row = await session.get(DataSourceSourceModel, source_id)
            return _source_from_row(row) if row is not None else None

    async def get_source_by_key(self, source_key: str) -> ManagedDataSourceSource | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(DataSourceSourceModel).where(DataSourceSourceModel.source_key == source_key)
            )
            return _source_from_row(row) if row is not None else None

    async def save_source(
        self,
        source: ManagedDataSourceSource,
    ) -> ManagedDataSourceSource:
        async with self._sessions() as session:
            row = await session.get(DataSourceSourceModel, source.id) if source.id else None
            if row is None:
                row = DataSourceSourceModel(source_key=source.source_key)
                session.add(row)
            _apply_source(row, source)
            await session.commit()
            await session.refresh(row)
            return _source_from_row(row)

    async def delete_source(self, source_id: str) -> bool:
        async with self._sessions() as session:
            row = await session.get(DataSourceSourceModel, source_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_bindings_page(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: str | None = None,
        scope_type: str = "all",
        organization_unit_id: str = "",
        search: str = "",
        status: str = "all",
        view_scopes: Sequence[AdminScopeRef] | None = None,
    ) -> DataSourcePage:
        model = DataSourceSourceBindingModel
        conditions = []
        if tenant_id:
            conditions.append(model.tenant_id == tenant_id)
        if scope_type != "all":
            conditions.append(model.scope_type == scope_type)
        if organization_unit_id:
            conditions.append(model.organization_unit_id == organization_unit_id)
        if status != "all":
            conditions.append(model.status == status)
        if view_scopes is not None:
            root_ids = tuple(
                scope.scope_organization_unit_id
                for scope in view_scopes
                if scope.scope_organization_unit_id
            )
            visible_ids = set(root_ids) | set(await self._areas.descendant_ids(root_ids))
            visibility = _binding_visibility_conditions(view_scopes, visible_ids)
            conditions.append(or_(*visibility) if visibility else false())
        keyword = search.strip().lower()
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            matching_organization_unit_ids = tuple(
                await self._areas.search_organization_unit_ids(keyword)
            )
            conditions.append(
                or_(
                    func.lower(model.tenant_id).like(pattern, escape="\\"),
                    func.lower(model.scope_type).like(pattern, escape="\\"),
                    func.lower(model.organization_unit_id).like(pattern, escape="\\"),
                    func.lower(model.data_source_id).like(pattern, escape="\\"),
                    model.organization_unit_id.in_(matching_organization_unit_ids),
                    func.lower(DataSourceSourceModel.source_key).like(pattern, escape="\\"),
                    func.lower(DataSourceSourceModel.display_name).like(
                        pattern,
                        escape="\\",
                    ),
                    func.lower(DataSourceSourceModel.default_database_key).like(
                        pattern,
                        escape="\\",
                    ),
                )
            )
        async with self._sessions() as session:
            base_statement = (
                select(model)
                .outerjoin(
                    DataSourceSourceModel,
                    DataSourceSourceModel.id == model.data_source_id,
                )
                .where(*conditions)
            )
            rows = tuple(
                await session.scalars(
                    base_statement.order_by(
                        model.tenant_id.asc(),
                        model.scope_type.asc(),
                        model.organization_unit_id.asc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .outerjoin(
                        DataSourceSourceModel,
                        DataSourceSourceModel.id == model.data_source_id,
                    )
                    .where(*conditions)
                )
                or 0
            )
        return DataSourcePage(
            items=tuple(_binding_from_row(row) for row in rows),
            total=total,
        )

    async def binding_exists(
        self,
        *,
        data_source_id: str,
        status: str | None = None,
        tenant_id: str | None = None,
        scope_type: str | None = None,
        organization_unit_id: str | None = None,
    ) -> bool:
        model = DataSourceSourceBindingModel
        conditions = [model.data_source_id == data_source_id]
        if status is not None:
            conditions.append(model.status == status)
        if tenant_id is not None:
            conditions.append(model.tenant_id == tenant_id)
        if scope_type is not None:
            conditions.append(model.scope_type == scope_type)
        if organization_unit_id is not None:
            conditions.append(model.organization_unit_id == organization_unit_id)
        async with self._sessions() as session:
            return bool(await session.scalar(select(exists().where(*conditions))))

    async def get_binding(
        self,
        binding_id: str,
    ) -> ManagedDataSourceSourceBinding | None:
        async with self._sessions() as session:
            row = await session.get(DataSourceSourceBindingModel, binding_id)
            return _binding_from_row(row) if row is not None else None

    async def get_binding_by_scope(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
    ) -> ManagedDataSourceSourceBinding | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(DataSourceSourceBindingModel).where(
                    DataSourceSourceBindingModel.tenant_id == tenant_id,
                    DataSourceSourceBindingModel.scope_type == scope_type,
                    DataSourceSourceBindingModel.organization_unit_id == organization_unit_id,
                )
            )
            return _binding_from_row(row) if row is not None else None

    async def save_binding(
        self,
        binding: ManagedDataSourceSourceBinding,
    ) -> ManagedDataSourceSourceBinding:
        async with self._sessions() as session:
            row = (
                await session.get(DataSourceSourceBindingModel, binding.id) if binding.id else None
            )
            if row is None:
                row = DataSourceSourceBindingModel(
                    tenant_id=binding.tenant_id,
                    scope_type=binding.scope_type,
                    organization_unit_id=binding.organization_unit_id,
                )
                session.add(row)
            _apply_binding(row, binding)
            await session.commit()
            await session.refresh(row)
            return _binding_from_row(row)

    async def delete_binding(self, binding_id: str) -> bool:
        async with self._sessions() as session:
            row = await session.get(DataSourceSourceBindingModel, binding_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_entitlements_page(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: str | None = None,
        scope_type: str = "all",
        organization_unit_id: str = "",
        search: str = "",
        status: str = "all",
        view_scopes: Sequence[AdminScopeRef] | None = None,
    ) -> DataSourcePage:
        model = DataSourceSourceEntitlementModel
        conditions = []
        if tenant_id:
            conditions.append(model.tenant_id == tenant_id)
        if scope_type != "all":
            conditions.append(model.scope_type == scope_type)
        if organization_unit_id:
            conditions.append(model.organization_unit_id == organization_unit_id)
        if status != "all":
            conditions.append(model.status == status)
        if view_scopes is not None:
            root_ids = tuple(
                dict.fromkeys(
                    scope.scope_organization_unit_id
                    for scope in view_scopes
                    if scope.scope_type is AdminScopeType.ORGANIZATION_UNIT
                    and scope.scope_organization_unit_id
                )
            )
            descendant_ids = await self._areas.descendant_ids(root_ids)
            visibility = _entitlement_visibility_conditions(
                view_scopes,
                set(root_ids) | set(descendant_ids),
            )
            conditions.append(or_(*visibility) if visibility else false())
        keyword = search.strip().lower()
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            matching_organization_unit_ids = tuple(
                await self._areas.search_organization_unit_ids(keyword)
            )
            conditions.append(
                or_(
                    func.lower(model.tenant_id).like(pattern, escape="\\"),
                    func.lower(model.scope_type).like(pattern, escape="\\"),
                    func.lower(model.organization_unit_id).like(pattern, escape="\\"),
                    func.lower(model.data_source_id).like(pattern, escape="\\"),
                    model.organization_unit_id.in_(matching_organization_unit_ids),
                    func.lower(DataSourceSourceModel.source_key).like(pattern, escape="\\"),
                    func.lower(DataSourceSourceModel.display_name).like(
                        pattern,
                        escape="\\",
                    ),
                )
            )
        async with self._sessions() as session:
            base_statement = (
                select(model)
                .outerjoin(
                    DataSourceSourceModel,
                    DataSourceSourceModel.id == model.data_source_id,
                )
                .where(*conditions)
            )
            rows = tuple(
                await session.scalars(
                    base_statement.order_by(
                        model.tenant_id.asc(),
                        model.scope_type.asc(),
                        model.organization_unit_id.asc(),
                        model.data_source_id.asc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .outerjoin(
                        DataSourceSourceModel,
                        DataSourceSourceModel.id == model.data_source_id,
                    )
                    .where(*conditions)
                )
                or 0
            )
        return DataSourcePage(
            items=tuple(_entitlement_from_row(row) for row in rows),
            total=total,
        )

    async def entitlement_exists(
        self,
        *,
        data_source_id: str,
        status: str | None = None,
        tenant_id: str | None = None,
        scope_type: str | None = None,
        organization_unit_ids: Sequence[str] | None = None,
        exclude_id: str | None = None,
    ) -> bool:
        model = DataSourceSourceEntitlementModel
        conditions = [model.data_source_id == data_source_id]
        if status is not None:
            conditions.append(model.status == status)
        if tenant_id is not None:
            conditions.append(model.tenant_id == tenant_id)
        if scope_type is not None:
            conditions.append(model.scope_type == scope_type)
        if organization_unit_ids is not None:
            conditions.append(model.organization_unit_id.in_(organization_unit_ids))
        if exclude_id is not None:
            conditions.append(model.id != exclude_id)
        async with self._sessions() as session:
            return bool(await session.scalar(select(exists().where(*conditions))))

    async def get_entitlement(
        self,
        entitlement_id: str,
    ) -> ManagedDataSourceSourceEntitlement | None:
        async with self._sessions() as session:
            row = await session.get(DataSourceSourceEntitlementModel, entitlement_id)
            return _entitlement_from_row(row) if row is not None else None

    async def get_entitlement_by_scope_source(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
        data_source_id: str,
    ) -> ManagedDataSourceSourceEntitlement | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(DataSourceSourceEntitlementModel).where(
                    DataSourceSourceEntitlementModel.tenant_id == tenant_id,
                    DataSourceSourceEntitlementModel.scope_type == scope_type,
                    DataSourceSourceEntitlementModel.organization_unit_id == organization_unit_id,
                    DataSourceSourceEntitlementModel.data_source_id == data_source_id,
                )
            )
            return _entitlement_from_row(row) if row is not None else None

    async def save_entitlement(
        self,
        entitlement: ManagedDataSourceSourceEntitlement,
    ) -> ManagedDataSourceSourceEntitlement:
        return (await self.save_entitlements((entitlement,)))[0]

    async def save_entitlements(
        self,
        entitlements: Sequence[ManagedDataSourceSourceEntitlement],
    ) -> Sequence[ManagedDataSourceSourceEntitlement]:
        rows: list[DataSourceSourceEntitlementModel] = []
        async with self._sessions() as session:
            for entitlement in entitlements:
                row = (
                    await session.get(DataSourceSourceEntitlementModel, entitlement.id)
                    if entitlement.id
                    else None
                )
                if row is None:
                    row = DataSourceSourceEntitlementModel(
                        tenant_id=entitlement.tenant_id,
                        scope_type=entitlement.scope_type,
                        organization_unit_id=entitlement.organization_unit_id,
                        data_source_id=entitlement.data_source_id,
                    )
                    session.add(row)
                _apply_entitlement(row, entitlement)
                rows.append(row)
            await session.commit()
            for row in rows:
                await session.refresh(row)
        return tuple(_entitlement_from_row(row) for row in rows)

    async def delete_entitlement(self, entitlement_id: str) -> bool:
        async with self._sessions() as session:
            row = await session.get(DataSourceSourceEntitlementModel, entitlement_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True


def _binding_visibility_conditions(
    view_scopes: Sequence[AdminScopeRef],
    visible_organization_unit_ids: set[str],
) -> list[Any]:
    model = DataSourceSourceBindingModel
    conditions = []
    for scope in view_scopes:
        tenant_condition = model.tenant_id == scope.scope_tenant_id
        if scope.scope_type is AdminScopeType.TENANT:
            conditions.append(tenant_condition)
        elif scope.scope_type is AdminScopeType.ORGANIZATION_UNIT:
            conditions.append(
                and_(
                    tenant_condition,
                    model.scope_type == "organization_unit",
                    model.organization_unit_id.in_(visible_organization_unit_ids),
                )
            )
    return conditions


def _entitlement_visibility_conditions(
    view_scopes: Sequence[AdminScopeRef],
    visible_organization_unit_ids: set[str],
) -> list[Any]:
    model = DataSourceSourceEntitlementModel
    conditions = []
    for scope in view_scopes:
        tenant_condition = model.tenant_id == scope.scope_tenant_id
        if scope.scope_type is AdminScopeType.TENANT:
            conditions.append(tenant_condition)
        elif scope.scope_type is AdminScopeType.ORGANIZATION_UNIT:
            conditions.append(
                and_(
                    tenant_condition,
                    model.scope_type == "organization_unit",
                    model.organization_unit_id.in_(visible_organization_unit_ids),
                )
            )
    return conditions


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _source_from_row(row: DataSourceSourceModel) -> ManagedDataSourceSource:
    values = {field_name: getattr(row, field_name) for field_name in DATA_SOURCE_FIELDS}
    return ManagedDataSourceSource(
        id=row.id,
        **values,
        created_at=row.create_time,
        updated_at=row.update_time,
    )


def _apply_source(row: DataSourceSourceModel, source: ManagedDataSourceSource) -> None:
    values = source.model_dump(include=set(DATA_SOURCE_FIELDS), mode="python")
    for field_name, value in values.items():
        setattr(row, field_name, value)


def _binding_from_row(
    row: DataSourceSourceBindingModel,
) -> ManagedDataSourceSourceBinding:
    return ManagedDataSourceSourceBinding(
        id=row.id,
        tenant_id=row.tenant_id,
        scope_type=row.scope_type,
        organization_unit_id=row.organization_unit_id,
        data_source_id=row.data_source_id,
        status=row.status,
        created_at=row.create_time,
        updated_at=row.update_time,
    )


def _apply_binding(
    row: DataSourceSourceBindingModel,
    binding: ManagedDataSourceSourceBinding,
) -> None:
    row.tenant_id = binding.tenant_id
    row.scope_type = binding.scope_type
    row.organization_unit_id = binding.organization_unit_id
    row.data_source_id = binding.data_source_id
    row.status = binding.status


def _entitlement_from_row(
    row: DataSourceSourceEntitlementModel,
) -> ManagedDataSourceSourceEntitlement:
    return ManagedDataSourceSourceEntitlement(
        id=row.id,
        tenant_id=row.tenant_id,
        scope_type=row.scope_type,
        organization_unit_id=row.organization_unit_id,
        data_source_id=row.data_source_id,
        status=row.status,
        created_at=row.create_time,
        updated_at=row.update_time,
    )


def _apply_entitlement(
    row: DataSourceSourceEntitlementModel,
    entitlement: ManagedDataSourceSourceEntitlement,
) -> None:
    row.tenant_id = entitlement.tenant_id
    row.scope_type = entitlement.scope_type
    row.organization_unit_id = entitlement.organization_unit_id
    row.data_source_id = entitlement.data_source_id
    row.status = entitlement.status
