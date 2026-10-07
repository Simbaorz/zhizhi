"""Platform persistence for physical sources and organization resource governance."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import JSON, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.ids import new_entity_id
from zhizhi_platform.data_source.domain import DataSourceConfig, SourceBinding, SourceEntitlement
from zhizhi_platform.database import ZhizhiBase


class DataSourceModel(ZhizhiBase):
    __tablename__ = "zhizhi_data_source"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    source_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DataSourceEntitlementModel(ZhizhiBase):
    __tablename__ = "zhizhi_data_source_entitlement"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "organization_unit_id",
            "source_id",
            name="uk_data_source_entitlement_scope",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_unit_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class DataSourceBindingModel(ZhizhiBase):
    __tablename__ = "zhizhi_data_source_binding"
    __table_args__ = (
        UniqueConstraint("tenant_id", "organization_unit_id", name="uk_data_source_binding_scope"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_unit_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DataSourceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def get_source(self, source_id: str) -> DataSourceConfig | None:
        async with self.sessions() as session:
            row = await session.get(DataSourceModel, source_id)
            return DataSourceConfig.model_validate(row.configuration) if row else None

    async def list_sources(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        source_ids: Sequence[str] | None = None,
    ) -> tuple[tuple[DataSourceConfig, ...], int]:
        conditions: list[Any] = []
        if source_ids is not None:
            conditions.append(DataSourceModel.id.in_(source_ids))
        if search:
            # Match the searchable non-secret fields only.
            conditions.append(
                DataSourceModel.source_key.contains(search, autoescape=True)
                | DataSourceModel.configuration["display_name"]
                .as_string()
                .contains(search, autoescape=True)
                | DataSourceModel.configuration["tag"].as_string().contains(search, autoescape=True)
            )
        async with self.sessions() as session:
            total = int(
                await session.scalar(
                    select(func.count()).select_from(DataSourceModel).where(*conditions)
                )
                or 0
            )
            rows = await session.scalars(
                select(DataSourceModel)
                .where(*conditions)
                .order_by(DataSourceModel.source_key, DataSourceModel.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return tuple(DataSourceConfig.model_validate(row.configuration) for row in rows), total

    async def save_source(self, source: DataSourceConfig) -> DataSourceConfig:
        async with self.sessions() as session:
            row = (
                await session.get(DataSourceModel, source.id, with_for_update=True)
                if source.id
                else None
            )
            if row is not None and row.configuration.get("revision", 1) != source.revision:
                raise ApplicationError(
                    ApplicationErrorKind.CONFLICT, "数据源配置已更新，请刷新后再保存。"
                )
            if row is None:
                row = DataSourceModel(id=source.id or new_entity_id())
                session.add(row)
            saved = source.model_copy(update={"id": row.id, "revision": source.revision + 1})
            row.source_key = saved.source_key
            row.configuration = saved.model_dump(mode="json")
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ApplicationError(ApplicationErrorKind.CONFLICT, "数据源编号已存在。") from exc
            return saved

    async def record_test(self, source_id: str, status: str, revision: int) -> None:
        async with self.sessions() as session:
            row = await session.get(DataSourceModel, source_id, with_for_update=True)
            if row is not None and row.configuration.get("revision", 1) == revision:
                row.configuration = {**row.configuration, "last_test_status": status}
                await session.commit()

    async def delete_source(self, source_id: str) -> None:
        async with self.sessions() as session:
            row = await session.get(DataSourceModel, source_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def list_entitlements(
        self,
        tenant_id: str,
        organization_unit_id: str | None = None,
        *,
        unit_ids: Sequence[str] | None = None,
        source_ids: Sequence[str] | None = None,
    ) -> tuple[SourceEntitlement, ...]:
        conditions = [DataSourceEntitlementModel.tenant_id == tenant_id]
        if organization_unit_id is not None:
            conditions.append(
                DataSourceEntitlementModel.organization_unit_id == organization_unit_id
            )
        if unit_ids is not None:
            conditions.append(DataSourceEntitlementModel.organization_unit_id.in_(unit_ids))
        if source_ids is not None:
            conditions.append(DataSourceEntitlementModel.source_id.in_(source_ids))
        async with self.sessions() as session:
            rows = await session.scalars(
                select(DataSourceEntitlementModel)
                .where(*conditions)
                .order_by(DataSourceEntitlementModel.source_id)
            )
            return tuple(
                SourceEntitlement(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    organization_unit_id=row.organization_unit_id,
                    source_id=row.source_id,
                )
                for row in rows
            )

    async def get_entitlement(
        self, tenant_id: str, unit_id: str, source_id: str
    ) -> SourceEntitlement | None:
        return next(
            (
                item
                for item in await self.list_entitlements(tenant_id, unit_id)
                if item.source_id == source_id
            ),
            None,
        )

    async def save_entitlement(self, entitlement: SourceEntitlement) -> SourceEntitlement:
        async with self.sessions() as session:
            row = DataSourceEntitlementModel(
                **entitlement.model_dump(exclude={"id"}), id=entitlement.id or new_entity_id()
            )
            session.add(row)
            await session.commit()
            return entitlement.model_copy(update={"id": row.id})

    async def delete_entitlement(self, entitlement_id: str) -> None:
        async with self.sessions() as session:
            row = await session.get(DataSourceEntitlementModel, entitlement_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def list_bindings(
        self, tenant_id: str | None = None, *, unit_ids: Sequence[str] | None = None
    ) -> tuple[SourceBinding, ...]:
        async with self.sessions() as session:
            statement = select(DataSourceBindingModel)
            if tenant_id is not None:
                statement = statement.where(DataSourceBindingModel.tenant_id == tenant_id)
            if unit_ids is not None:
                statement = statement.where(
                    DataSourceBindingModel.organization_unit_id.in_(unit_ids)
                )
            rows = await session.scalars(
                statement.order_by(
                    DataSourceBindingModel.tenant_id, DataSourceBindingModel.organization_unit_id
                )
            )
            return tuple(SourceBinding.model_validate(row.configuration) for row in rows)

    async def save_binding(self, binding: SourceBinding) -> SourceBinding:
        async with self.sessions() as session:
            row = await session.scalar(
                select(DataSourceBindingModel).where(
                    DataSourceBindingModel.tenant_id == binding.tenant_id,
                    DataSourceBindingModel.organization_unit_id == binding.organization_unit_id,
                )
            )
            if row is None:
                row = DataSourceBindingModel(
                    id=new_entity_id(),
                    tenant_id=binding.tenant_id,
                    organization_unit_id=binding.organization_unit_id,
                )
                session.add(row)
            saved = binding.model_copy(update={"id": row.id})
            row.configuration = saved.model_dump(mode="json")
            await session.commit()
            return saved

    async def delete_binding(self, binding_id: str) -> None:
        async with self.sessions() as session:
            row = await session.get(DataSourceBindingModel, binding_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def allocated(self, source_id: str) -> bool:
        async with self.sessions() as session:
            return bool(
                await session.scalar(
                    select(DataSourceEntitlementModel.id)
                    .where(DataSourceEntitlementModel.source_id == source_id)
                    .limit(1)
                )
            )
