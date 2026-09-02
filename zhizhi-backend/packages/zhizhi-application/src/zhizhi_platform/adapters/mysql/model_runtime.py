"""Minimal MySQL reads used by one 致知 model-bound turn."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from zhizhi_platform.adapters.mysql.models import LLMBindingModel, LLMConfigModel
from zhizhi_platform.iam import OrganizationDirectory
from zhizhi_platform.llm.capability import ZhizhiModelConfigRecord
from zhizhi_platform.llm.resolution import (
    ZhizhiModelBindingRecord,
)

SessionFactory = Callable[[], AsyncSession]


class MysqlModelRuntimeRepository:
    """Read only the 致知 model catalog needed by one Agent turn."""

    def __init__(
        self,
        session_factory: SessionFactory,
        organization_directory: OrganizationDirectory,
    ) -> None:
        self._session_factory = session_factory
        self._organization_directory = organization_directory

    async def get_config(self, config_id: str) -> ZhizhiModelConfigRecord | None:
        async with self._session_factory() as session:
            row = await session.get(LLMConfigModel, config_id)
            return _config_from_row(row) if row is not None else None  # noqa

    async def list_active_bindings_for_scopes(
        self,
        tenant_id: str,
        scope_keys: Sequence[tuple[str, str]],
    ) -> Sequence[ZhizhiModelBindingRecord]:
        if not scope_keys:
            return ()
        async with self._session_factory() as session:
            rows = tuple(
                await session.scalars(
                    select(LLMBindingModel)
                    .where(
                        LLMBindingModel.tenant_id == tenant_id,
                        LLMBindingModel.status == "active",
                        tuple_(
                            LLMBindingModel.scope_type, LLMBindingModel.organization_unit_id
                        ).in_(scope_keys),
                    )
                    .order_by(
                        LLMBindingModel.scope_type.asc(), LLMBindingModel.organization_unit_id.asc()
                    )
                )
            )
        return tuple(_binding_from_row(row) for row in rows)


def _config_from_row(row: LLMConfigModel) -> ZhizhiModelConfigRecord:
    return ZhizhiModelConfigRecord(
        config_id=row.id,
        alias=row.alias,
        provider=row.provider,
        protocol=row.protocol,
        model_name=row.model_name,
        endpoint_url=row.endpoint_url,
        status=row.status,
        support_stream=row.support_stream,
        support_tools=row.support_tools,
        support_vision=row.support_vision,
        timeout_seconds=row.timeout_seconds,
        generation_config=dict(row.generation_config or {}),
        provider_config=dict(row.provider_config or {}),
        credentials_ciphertext=row.credentials_ciphertext,
        credential_status=row.credential_status,
    )


def _binding_from_row(row: LLMBindingModel) -> ZhizhiModelBindingRecord:
    return ZhizhiModelBindingRecord(
        binding_id=row.id,
        tenant_id=row.tenant_id,
        scope_type=row.scope_type,
        organization_unit_id=row.organization_unit_id,
        model_config_id=row.llm_config_id,
        status=row.status,
        runtime_overrides=dict(row.runtime_overrides or {}),
    )
