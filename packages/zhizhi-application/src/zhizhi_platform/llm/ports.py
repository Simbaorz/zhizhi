"""Outbound boundaries for Zhizhi-managed model administration."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from zhizhi_platform.iam.models import AdminScopeRef, ManagedOrganizationUnit, ManagedTenant
from zhizhi_platform.llm.domain import (
    ManagedLLMBinding,
    ManagedLLMConfig,
    ManagedLLMEntitlement,
)

ItemT = TypeVar("ItemT")


class LLMPage(BaseModel):
    """One SQL-filtered page of managed LLM rows."""

    model_config = ConfigDict(frozen=True)

    items: tuple[Any, ...] = Field(default_factory=tuple)
    total: int = Field(default=0, ge=0)


class LLMAdminRepository(Protocol):
    """Store and query Zhizhi model configs, entitlements, and bindings."""

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
    ) -> LLMPage: ...

    async def get_config(self, config_id: str) -> ManagedLLMConfig | None: ...

    async def get_config_by_alias(self, alias: str) -> ManagedLLMConfig | None: ...

    async def save_config(self, config: ManagedLLMConfig) -> ManagedLLMConfig: ...

    async def delete_config(self, config_id: str) -> bool: ...

    async def update_test_result(
        self,
        config_id: str,
        *,
        status: str,
        message: str,
        tested_at: datetime,
    ) -> ManagedLLMConfig | None: ...

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
    ) -> LLMPage: ...

    async def binding_exists(
        self,
        *,
        llm_config_id: str,
        status: str | None = None,
        tenant_id: str | None = None,
        scope_type: str | None = None,
        organization_unit_id: str | None = None,
    ) -> bool: ...

    async def get_binding(self, binding_id: str) -> ManagedLLMBinding | None: ...

    async def get_binding_by_scope(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
    ) -> ManagedLLMBinding | None: ...

    async def save_binding(self, binding: ManagedLLMBinding) -> ManagedLLMBinding: ...

    async def delete_binding(self, binding_id: str) -> bool: ...

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
    ) -> LLMPage: ...

    async def entitlement_exists(
        self,
        *,
        llm_config_id: str,
        status: str | None = None,
        tenant_id: str | None = None,
        scope_type: str | None = None,
        organization_unit_ids: Sequence[str] | None = None,
        exclude_id: str | None = None,
    ) -> bool: ...

    async def get_entitlement(self, entitlement_id: str) -> ManagedLLMEntitlement | None: ...

    async def get_entitlement_by_scope_model(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
        llm_config_id: str,
    ) -> ManagedLLMEntitlement | None: ...

    async def save_entitlement(
        self,
        entitlement: ManagedLLMEntitlement,
    ) -> ManagedLLMEntitlement: ...

    async def save_entitlements(
        self,
        entitlements: Sequence[ManagedLLMEntitlement],
    ) -> Sequence[ManagedLLMEntitlement]: ...

    async def delete_entitlement(self, entitlement_id: str) -> bool: ...


class ZhizhiLLMOrganizationDirectory(Protocol):
    """Zhizhi organization facts required by model hierarchy policy."""

    async def get_tenant(self, tenant_id: str) -> ManagedTenant | None: ...

    async def get_organization_unit(
        self, organization_unit_id: str
    ) -> ManagedOrganizationUnit | None: ...

    async def get_organization_path(
        self, tenant_id: str, organization_unit_id: str
    ) -> tuple[ManagedOrganizationUnit, ...]: ...

    async def descendant_ids(self, organization_unit_ids: Sequence[str]) -> Sequence[str]: ...


class LLMCredentialCipher(Protocol):
    """Encrypt and decrypt stored model credential mappings."""

    def encrypt(self, payload: dict[str, Any]) -> str: ...

    def decrypt(self, ciphertext: str) -> dict[str, Any]: ...


class LLMConnectivityTimeoutError(Exception):
    """The provider request exceeded its configured timeout."""


class LLMConnectivityNetworkError(Exception):
    """The provider endpoint could not be reached."""


class LLMConnectivityRequest(BaseModel):
    """Normalized configuration for one model connectivity test."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model_name: str
    endpoint_url: str
    timeout_seconds: int
    generation_config: dict[str, Any] = Field(default_factory=dict)
    provider_config: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] = Field(default_factory=dict, exclude=True, repr=False)
    prompt: str
    system_prompt: str = ""


class LLMConnectivityResult(BaseModel):
    """Provider-neutral result from one connectivity test."""

    model_config = ConfigDict(frozen=True)

    content: str = ""
    usage: dict[str, int] | None = None


class LLMConnectivityTester(Protocol):
    """Execute one provider-specific model connectivity test."""

    async def test(self, request: LLMConnectivityRequest) -> LLMConnectivityResult: ...
