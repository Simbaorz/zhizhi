"""Resolved tenant, organization, and principal scope contracts."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from zhizhi_platform.iam import OrganizationUnitRef


class AgentScope(BaseModel):
    """Validated active organization path for one caller."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(min_length=1)
    tenant_code: str = Field(min_length=1)
    tenant_storage_key: str = Field(min_length=1)
    organization_path: tuple[OrganizationUnitRef, ...] = Field(default_factory=tuple)
    principal_id: str = Field(min_length=1)
    principal_type: str = "user"


class AgentScopeResolver(Protocol):
    """Resolve a trusted tenant and active organization unit."""

    async def resolve(
        self,
        *,
        tenant_id: str,
        active_organization_unit_id: str,
        principal_id: str,
        principal_type: str,
    ) -> AgentScope | None: ...
