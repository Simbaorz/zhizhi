"""Nearest-ancestor model binding resolution for arbitrary organization trees."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gewu_core import ApplicationError, ApplicationErrorKind
from zhizhi_platform.iam.identity import AccessScope
from zhizhi_platform.runtime_contracts import ZhizhiResolvedModel

ACTIVE_STATUS = "active"
BINDING_SCOPE_TENANT = "tenant"
BINDING_SCOPE_ORGANIZATION_UNIT = "organization_unit"


class ZhizhiModelBindingRecord(BaseModel):
    """Model binding fields needed before creating a provider capability."""

    model_config = ConfigDict(frozen=True)

    binding_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    scope_type: str
    organization_unit_id: str = ""
    model_config_id: str = Field(min_length=1)
    status: str = ACTIVE_STATUS
    runtime_overrides: dict[str, object] = Field(default_factory=dict)


class ZhizhiModelRuntimeRepository(Protocol):
    """Read-side operations required by model selection."""

    async def list_active_bindings_for_scopes(
        self,
        tenant_id: str,
        scope_keys: Sequence[tuple[str, str]],
    ) -> Sequence[ZhizhiModelBindingRecord]: ...


class ZhizhiModelCapabilityFactory(Protocol):
    """Build an authorized runtime model from one binding."""

    async def create(
        self,
        binding: ZhizhiModelBindingRecord,
    ) -> ZhizhiResolvedModel | None: ...


class ZhizhiModelBindingResolver:
    """Resolve leaf-to-root, then tenant, without encoding hierarchy depth."""

    def __init__(
        self,
        repository: ZhizhiModelRuntimeRepository,
        capability_factory: ZhizhiModelCapabilityFactory,
    ) -> None:
        self._repository = repository
        self._capabilities = capability_factory

    async def resolve(self, actor_scope: AccessScope) -> ZhizhiResolvedModel | None:
        candidates = self._candidate_scopes(actor_scope)
        bindings = await self._repository.list_active_bindings_for_scopes(
            actor_scope.tenant_id,
            candidates,
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
            resolved = await self._capabilities.create(binding)
            if resolved is None:
                raise ApplicationError(
                    ApplicationErrorKind.UNAVAILABLE,
                    "The nearest active model binding is unavailable.",
                )
            return resolved
        return None

    @staticmethod
    def _candidate_scopes(actor_scope: AccessScope) -> list[tuple[str, str]]:
        candidates = [
            (BINDING_SCOPE_ORGANIZATION_UNIT, unit.id)
            for unit in reversed(actor_scope.organization_path)
        ]
        candidates.append((BINDING_SCOPE_TENANT, ""))
        return candidates
