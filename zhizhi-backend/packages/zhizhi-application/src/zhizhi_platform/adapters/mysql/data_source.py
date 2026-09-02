"""Minimal MySQL reads used by one 致知 Data Source turn."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from zhizhi_platform.adapters.mysql.models import (
    DataSourceSourceBindingModel,
    DataSourceSourceModel,
)
from zhizhi_platform.data_source.resolution import (
    ZhizhiDataSourceBindingRecord,
    ZhizhiDataSourceSourceRecord,
)

SessionFactory = Callable[[], AsyncSession]


class MysqlDataSourceRuntimeRepository:
    """Read only the 致知 source data required by one Agent turn."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def get_source(self, source_id: str) -> ZhizhiDataSourceSourceRecord | None:
        async with self._session_factory() as session:
            row = await session.get(DataSourceSourceModel, source_id)
            return _source_from_row(row) if row is not None else None

    async def list_active_bindings_for_scopes(
        self,
        tenant_id: str,
        scope_keys: Sequence[tuple[str, str]],
    ) -> Sequence[ZhizhiDataSourceBindingRecord]:
        if not scope_keys:
            return ()
        async with self._session_factory() as session:
            rows = tuple(
                await session.scalars(
                    select(DataSourceSourceBindingModel).where(
                        DataSourceSourceBindingModel.tenant_id == tenant_id,
                        DataSourceSourceBindingModel.status == "active",
                        tuple_(
                            DataSourceSourceBindingModel.scope_type,
                            DataSourceSourceBindingModel.organization_unit_id,
                        ).in_(scope_keys),
                    )
                )
            )
        return tuple(_binding_from_row(row) for row in rows)


def _source_from_row(row: DataSourceSourceModel) -> ZhizhiDataSourceSourceRecord:
    return ZhizhiDataSourceSourceRecord(
        source_id=row.id,
        source_key=row.source_key,
        display_name=row.display_name,
        description=row.description,
        status=row.status,
        api_url=row.api_url,
        app_id=row.app_id,
        credentials_ciphertext=row.credentials_ciphertext,
        credential_status=row.credential_status,
        default_database_key=row.default_database_key,
        exec_sources_code=row.exec_sources_code,
        timeout_seconds=row.timeout_seconds,
        default_max_rows=row.default_max_rows,
        hard_max_rows=row.hard_max_rows,
        allow_databases=row.allow_databases,
        log_sql=row.log_sql,
    )


def _binding_from_row(
    row: DataSourceSourceBindingModel,
) -> ZhizhiDataSourceBindingRecord:
    return ZhizhiDataSourceBindingRecord(
        binding_id=row.id,
        tenant_id=row.tenant_id,
        scope_type=row.scope_type,
        organization_unit_id=row.organization_unit_id,
        data_source_id=row.data_source_id,
        status=row.status,
    )
