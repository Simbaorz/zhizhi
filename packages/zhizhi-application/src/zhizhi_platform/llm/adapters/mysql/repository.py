"""SQLAlchemy persistence for 致知-managed model resources."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zhizhi_platform.iam import AdminScopeRef, AdminScopeType, OrganizationDirectory
from zhizhi_platform.llm.adapters.mysql.models import (
    LLMBindingModel,
    LLMConfigModel,
    LLMEntitlementModel,
)
from zhizhi_platform.llm.domain import (
    ManagedLLMBinding,
    ManagedLLMConfig,
    ManagedLLMEntitlement,
)
from zhizhi_platform.llm.ports import LLMPage

SessionFactory = Callable[[], AsyncSession]


class MysqlLLMAdminRepository:
    """Store and page all 致知 model-management resources."""

    def __init__(
        self,
        session_factory: SessionFactory,
        organization_directory: OrganizationDirectory,
    ) -> None:
        self._sessions = session_factory
        self._areas = organization_directory

    async def list_configs_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
        provider: str = "all",
        tenant_id: str | None = None,
        view_scopes: Sequence[AdminScopeRef] | None = None,
        include_endpoint_in_search: bool = True,
    ) -> LLMPage:
        conditions = []
        if status != "all":
            conditions.append(LLMConfigModel.status == status)
        if provider != "all":
            conditions.append(LLMConfigModel.provider == provider)
        keyword = search.strip().lower()
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            search_conditions = [
                func.lower(LLMConfigModel.alias).like(pattern, escape="\\"),
                func.lower(LLMConfigModel.display_name).like(pattern, escape="\\"),
                func.lower(LLMConfigModel.model_name).like(pattern, escape="\\"),
            ]
            if include_endpoint_in_search:
                search_conditions.append(
                    func.lower(LLMConfigModel.endpoint_url).like(pattern, escape="\\")
                )
            conditions.append(or_(*search_conditions))
        if tenant_id is not None:
            entitlement_conditions = [
                LLMEntitlementModel.llm_config_id == LLMConfigModel.id,
                LLMEntitlementModel.tenant_id == tenant_id,
            ]
            if view_scopes is not None:
                entitlement_conditions.append(
                    await self._scope_visibility_condition(LLMEntitlementModel, view_scopes)
                )
            conditions.append(exists(select(1).where(*entitlement_conditions)))
        async with self._sessions() as session:
            base_statement = select(LLMConfigModel).where(*conditions)
            rows = tuple(
                await session.scalars(
                    base_statement.order_by(LLMConfigModel.id.asc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            total = int(
                await session.scalar(
                    select(func.count()).select_from(LLMConfigModel).where(*conditions)
                )
                or 0
            )
        return LLMPage(items=tuple(_config_from_row(row) for row in rows), total=total)

    async def get_config(self, config_id: str) -> ManagedLLMConfig | None:
        async with self._sessions() as session:
            row = await session.get(LLMConfigModel, config_id)
            return _config_from_row(row) if row is not None else None

    async def get_config_by_alias(self, alias: str) -> ManagedLLMConfig | None:
        async with self._sessions() as session:
            row = await session.scalar(select(LLMConfigModel).where(LLMConfigModel.alias == alias))
            return _config_from_row(row) if row is not None else None

    async def save_config(self, config: ManagedLLMConfig) -> ManagedLLMConfig:
        async with self._sessions() as session:
            row = await session.get(LLMConfigModel, config.id) if config.id else None
            if row is None:
                row = LLMConfigModel(alias=config.alias)
                session.add(row)
            _apply_config(row, config)
            await session.commit()
            await session.refresh(row)
            return _config_from_row(row)

    async def delete_config(self, config_id: str) -> bool:
        async with self._sessions() as session:
            row = await session.get(LLMConfigModel, config_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def update_test_result(
        self,
        config_id: str,
        *,
        status: str,
        message: str,
        tested_at: datetime,
    ) -> ManagedLLMConfig | None:
        async with self._sessions() as session:
            row = await session.get(LLMConfigModel, config_id)
            if row is None:
                return None
            row.last_test_status = status
            row.last_test_message = message[:512]
            row.last_test_time = tested_at
            await session.commit()
            await session.refresh(row)
            return _config_from_row(row)

    async def list_bindings_page(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: str | None = None,
        search: str = "",
        status: str = "all",
        scope_type: str = "all",
        organization_unit_id: str = "",
        view_scopes: Sequence[AdminScopeRef] | None = None,
    ) -> LLMPage:
        return await self._list_scope_rows_page(
            LLMBindingModel,
            page=page,
            page_size=page_size,
            tenant_id=tenant_id,
            search=search,
            status=status,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
            view_scopes=view_scopes,
            converter=_binding_from_row,
        )

    async def binding_exists(
        self,
        *,
        llm_config_id: str,
        status: str | None = None,
        tenant_id: str | None = None,
        scope_type: str | None = None,
        organization_unit_id: str | None = None,
    ) -> bool:
        conditions = [LLMBindingModel.llm_config_id == llm_config_id]
        if status is not None:
            conditions.append(LLMBindingModel.status == status)
        if tenant_id is not None:
            conditions.append(LLMBindingModel.tenant_id == tenant_id)
        if scope_type is not None:
            conditions.append(LLMBindingModel.scope_type == scope_type)
        if organization_unit_id is not None:
            conditions.append(LLMBindingModel.organization_unit_id == organization_unit_id)
        async with self._sessions() as session:
            return bool(await session.scalar(select(exists().where(*conditions))))

    async def get_binding(self, binding_id: str) -> ManagedLLMBinding | None:
        async with self._sessions() as session:
            row = await session.get(LLMBindingModel, binding_id)
            return _binding_from_row(row) if row is not None else None

    async def get_binding_by_scope(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
    ) -> ManagedLLMBinding | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(LLMBindingModel).where(
                    LLMBindingModel.tenant_id == tenant_id,
                    LLMBindingModel.scope_type == scope_type,
                    LLMBindingModel.organization_unit_id == organization_unit_id,
                )
            )
            return _binding_from_row(row) if row is not None else None

    async def save_binding(self, binding: ManagedLLMBinding) -> ManagedLLMBinding:
        async with self._sessions() as session:
            row = await session.get(LLMBindingModel, binding.id) if binding.id else None
            if row is None:
                row = LLMBindingModel(
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
            row = await session.get(LLMBindingModel, binding_id)
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
        search: str = "",
        status: str = "all",
        scope_type: str = "all",
        organization_unit_id: str = "",
        view_scopes: Sequence[AdminScopeRef] | None = None,
    ) -> LLMPage:
        return await self._list_scope_rows_page(
            LLMEntitlementModel,
            page=page,
            page_size=page_size,
            tenant_id=tenant_id,
            search=search,
            status=status,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
            view_scopes=view_scopes,
            converter=_entitlement_from_row,
        )

    async def entitlement_exists(
        self,
        *,
        llm_config_id: str,
        status: str | None = None,
        tenant_id: str | None = None,
        scope_type: str | None = None,
        organization_unit_ids: Sequence[str] | None = None,
        exclude_id: str | None = None,
    ) -> bool:
        conditions = [LLMEntitlementModel.llm_config_id == llm_config_id]
        if status is not None:
            conditions.append(LLMEntitlementModel.status == status)
        if tenant_id is not None:
            conditions.append(LLMEntitlementModel.tenant_id == tenant_id)
        if scope_type is not None:
            conditions.append(LLMEntitlementModel.scope_type == scope_type)
        if organization_unit_ids is not None:
            conditions.append(LLMEntitlementModel.organization_unit_id.in_(organization_unit_ids))
        if exclude_id is not None:
            conditions.append(LLMEntitlementModel.id != exclude_id)
        async with self._sessions() as session:
            return bool(await session.scalar(select(exists().where(*conditions))))

    async def get_entitlement(self, entitlement_id: str) -> ManagedLLMEntitlement | None:
        async with self._sessions() as session:
            row = await session.get(LLMEntitlementModel, entitlement_id)
            return _entitlement_from_row(row) if row is not None else None

    async def get_entitlement_by_scope_model(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
        llm_config_id: str,
    ) -> ManagedLLMEntitlement | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(LLMEntitlementModel).where(
                    LLMEntitlementModel.tenant_id == tenant_id,
                    LLMEntitlementModel.scope_type == scope_type,
                    LLMEntitlementModel.organization_unit_id == organization_unit_id,
                    LLMEntitlementModel.llm_config_id == llm_config_id,
                )
            )
            return _entitlement_from_row(row) if row is not None else None

    async def save_entitlement(
        self,
        entitlement: ManagedLLMEntitlement,
    ) -> ManagedLLMEntitlement:
        return (await self.save_entitlements((entitlement,)))[0]

    async def save_entitlements(
        self,
        entitlements: Sequence[ManagedLLMEntitlement],
    ) -> Sequence[ManagedLLMEntitlement]:
        rows: list[LLMEntitlementModel] = []
        async with self._sessions() as session:
            for entitlement in entitlements:
                row = (
                    await session.get(LLMEntitlementModel, entitlement.id)
                    if entitlement.id
                    else None
                )
                if row is None:
                    row = LLMEntitlementModel(
                        tenant_id=entitlement.tenant_id,
                        scope_type=entitlement.scope_type,
                        organization_unit_id=entitlement.organization_unit_id,
                        llm_config_id=entitlement.llm_config_id,
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
            row = await session.get(LLMEntitlementModel, entitlement_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def _scope_visibility_condition(
        self,
        model: Any,
        view_scopes: Sequence[AdminScopeRef],
    ) -> Any:
        root_ids = tuple(
            dict.fromkeys(
                scope.scope_organization_unit_id
                for scope in view_scopes
                if scope.scope_type is AdminScopeType.ORGANIZATION_UNIT
                and scope.scope_organization_unit_id
            )
        )
        descendant_ids = await self._areas.descendant_ids(root_ids)
        visible_ids = set(root_ids) | set(descendant_ids)
        conditions = _visibility_conditions(model, view_scopes, visible_ids)
        return or_(*conditions) if conditions else false()

    async def _list_scope_rows_page(
        self,
        model: Any,
        *,
        page: int,
        page_size: int,
        tenant_id: str | None,
        search: str,
        status: str,
        scope_type: str,
        organization_unit_id: str,
        view_scopes: Sequence[AdminScopeRef] | None,
        converter: Callable[[Any], Any],
    ) -> LLMPage:
        conditions = []
        if tenant_id:
            conditions.append(model.tenant_id == tenant_id)
        if status != "all":
            conditions.append(model.status == status)
        if scope_type != "all":
            conditions.append(model.scope_type == scope_type)
        if organization_unit_id:
            conditions.append(model.organization_unit_id == organization_unit_id)
        if view_scopes is not None:
            conditions.append(await self._scope_visibility_condition(model, view_scopes))
        keyword = search.strip().lower()
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            matching_organization_unit_ids = tuple(
                await self._areas.search_organization_unit_ids(keyword, include_descendants=True)
            )
            conditions.append(
                or_(
                    func.lower(model.tenant_id).like(pattern, escape="\\"),
                    func.lower(model.scope_type).like(pattern, escape="\\"),
                    func.lower(model.organization_unit_id).like(pattern, escape="\\"),
                    func.lower(model.llm_config_id).like(pattern, escape="\\"),
                    model.organization_unit_id.in_(matching_organization_unit_ids),
                    func.lower(LLMConfigModel.display_name).like(pattern, escape="\\"),
                    func.lower(LLMConfigModel.alias).like(pattern, escape="\\"),
                    func.lower(LLMConfigModel.model_name).like(pattern, escape="\\"),
                )
            )
        async with self._sessions() as session:
            base_statement = (
                select(model)
                .outerjoin(LLMConfigModel, LLMConfigModel.id == model.llm_config_id)
                .where(*conditions)
            )
            rows = tuple(
                await session.scalars(
                    base_statement.order_by(
                        model.tenant_id.asc(),
                        model.scope_type.asc(),
                        model.organization_unit_id.asc(),
                        model.id.asc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .outerjoin(LLMConfigModel, LLMConfigModel.id == model.llm_config_id)
                    .where(*conditions)
                )
                or 0
            )
        return LLMPage(items=tuple(converter(row) for row in rows), total=total)


def _visibility_conditions(
    model: Any,
    view_scopes: Sequence[AdminScopeRef],
    visible_organization_unit_ids: set[str],
) -> list[Any]:
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


def _config_from_row(row: LLMConfigModel) -> ManagedLLMConfig:
    return ManagedLLMConfig(
        id=row.id,
        alias=row.alias,
        display_name=row.display_name,
        provider=row.provider,
        protocol=row.protocol,
        model_name=row.model_name,
        endpoint_url=row.endpoint_url,
        status=row.status,
        support_stream=row.support_stream,
        support_tools=row.support_tools,
        support_vision=row.support_vision,
        support_thinking=row.support_thinking,
        timeout_seconds=row.timeout_seconds,
        generation_config=dict(row.generation_config or {}),
        provider_config=dict(row.provider_config or {}),
        credentials_ciphertext=row.credentials_ciphertext,
        credential_status=row.credential_status,
        last_test_status=row.last_test_status,
        last_test_message=row.last_test_message,
        last_test_time=row.last_test_time,
        created_at=row.create_time,
        updated_at=row.update_time,
    )


def _apply_config(row: LLMConfigModel, config: ManagedLLMConfig) -> None:
    for field_name in (
        "alias",
        "display_name",
        "provider",
        "protocol",
        "model_name",
        "endpoint_url",
        "status",
        "support_stream",
        "support_tools",
        "support_vision",
        "support_thinking",
        "timeout_seconds",
        "credentials_ciphertext",
        "credential_status",
        "last_test_status",
        "last_test_message",
        "last_test_time",
    ):
        setattr(row, field_name, getattr(config, field_name))
    row.generation_config = dict(config.generation_config)
    row.provider_config = dict(config.provider_config)


def _binding_from_row(row: LLMBindingModel) -> ManagedLLMBinding:
    return ManagedLLMBinding(
        id=row.id,
        tenant_id=row.tenant_id,
        scope_type=row.scope_type,
        organization_unit_id=row.organization_unit_id,
        llm_config_id=row.llm_config_id,
        status=row.status,
        runtime_overrides=dict(row.runtime_overrides or {}),
        created_at=row.create_time,
        updated_at=row.update_time,
    )


def _apply_binding(row: LLMBindingModel, binding: ManagedLLMBinding) -> None:
    row.tenant_id = binding.tenant_id
    row.scope_type = binding.scope_type
    row.organization_unit_id = binding.organization_unit_id
    row.llm_config_id = binding.llm_config_id
    row.status = binding.status
    row.runtime_overrides = dict(binding.runtime_overrides)


def _entitlement_from_row(row: LLMEntitlementModel) -> ManagedLLMEntitlement:
    return ManagedLLMEntitlement(
        id=row.id,
        tenant_id=row.tenant_id,
        scope_type=row.scope_type,
        organization_unit_id=row.organization_unit_id,
        llm_config_id=row.llm_config_id,
        status=row.status,
        created_at=row.create_time,
        updated_at=row.update_time,
    )


def _apply_entitlement(row: LLMEntitlementModel, entitlement: ManagedLLMEntitlement) -> None:
    row.tenant_id = entitlement.tenant_id
    row.scope_type = entitlement.scope_type
    row.organization_unit_id = entitlement.organization_unit_id
    row.llm_config_id = entitlement.llm_config_id
    row.status = entitlement.status
