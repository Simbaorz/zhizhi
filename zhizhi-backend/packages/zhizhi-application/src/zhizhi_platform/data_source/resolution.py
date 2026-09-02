"""Nearest-ancestor Data Source binding resolution."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gewu_core import ApplicationError, ApplicationErrorKind
from zhizhi_platform.iam.identity import AccessScope
from zhizhi_platform.runtime_contracts import ZhizhiDataSourceBinding

ACTIVE_STATUS = "active"


class ZhizhiDataSourceBindingRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    binding_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    scope_type: str
    organization_unit_id: str = ""
    data_source_id: str = Field(min_length=1)
    status: str = ACTIVE_STATUS


class ZhizhiDataSourceSourceRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    status: str = ACTIVE_STATUS
    api_url: str = ""
    app_id: str = ""
    credentials_ciphertext: str = ""
    credential_status: str = "missing"
    default_database_key: str = ""
    exec_sources_code: str = ""
    timeout_seconds: int = 30
    default_max_rows: int = 50
    hard_max_rows: int = 500
    allow_databases: str = ""
    log_sql: bool = False


class ZhizhiDataSourceRuntimeRepository(Protocol):
    async def list_active_bindings_for_scopes(
        self,
        tenant_id: str,
        scope_keys: Sequence[tuple[str, str]],
    ) -> Sequence[ZhizhiDataSourceBindingRecord]: ...


class ZhizhiDataSourceCapabilityFactory(Protocol):
    async def create(
        self,
        binding: ZhizhiDataSourceBindingRecord,
    ) -> ZhizhiDataSourceBinding | None: ...


class ZhizhiDataSourceSourceResolver:
    """Resolve the closest active binding along the current organization path."""

    def __init__(
        self,
        repository: ZhizhiDataSourceRuntimeRepository,
        capability_factory: ZhizhiDataSourceCapabilityFactory,
    ) -> None:
        self._repository = repository
        self._capabilities = capability_factory

    async def resolve(self, actor_scope: AccessScope) -> ZhizhiDataSourceBinding | None:
        candidates = [
            ("organization_unit", unit.id) for unit in reversed(actor_scope.organization_path)
        ]
        candidates.append(("tenant", ""))
        bindings = await self._repository.list_active_bindings_for_scopes(
            actor_scope.tenant_id, candidates
        )
        by_scope = {
            (binding.scope_type, binding.organization_unit_id): binding
            for binding in bindings
            if binding.status == ACTIVE_STATUS
        }
        for candidate in candidates:
            binding = by_scope.get(candidate)
            if binding is None:
                continue
            capability = await self._capabilities.create(binding)
            if capability is None:
                raise ApplicationError(
                    ApplicationErrorKind.UNAVAILABLE,
                    "The nearest active data-source binding is unavailable.",
                )
            return capability
        return None
