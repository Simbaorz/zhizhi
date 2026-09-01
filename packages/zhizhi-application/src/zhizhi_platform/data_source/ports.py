"""Outbound contracts for Zhizhi Data Source administration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from zhizhi_platform.data_source.domain import (
    ManagedDataSourceSource,
    ManagedDataSourceSourceBinding,
    ManagedDataSourceSourceEntitlement,
)
from zhizhi_platform.iam.models import AdminScopeRef, ManagedOrganizationUnit, ManagedTenant


class DataSourcePage(BaseModel):
    """One SQL-filtered page of managed Data Source rows."""

    model_config = ConfigDict(frozen=True)

    items: tuple[Any, ...] = Field(default_factory=tuple)
    total: int = Field(default=0, ge=0)


class DataSourceAdminRepository(Protocol):
    """Store and query all Zhizhi Data Source management resources."""

    async def list_sources_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> DataSourcePage: ...

    async def get_source(self, source_id: str) -> ManagedDataSourceSource | None: ...

    async def get_source_by_key(self, source_key: str) -> ManagedDataSourceSource | None: ...

    async def save_source(
        self,
        source: ManagedDataSourceSource,
    ) -> ManagedDataSourceSource: ...

    async def delete_source(self, source_id: str) -> bool: ...

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
    ) -> DataSourcePage: ...

    async def binding_exists(
        self,
        *,
        data_source_id: str,
        status: str | None = None,
        tenant_id: str | None = None,
        scope_type: str | None = None,
        organization_unit_id: str | None = None,
    ) -> bool: ...

    async def get_binding(
        self,
        binding_id: str,
    ) -> ManagedDataSourceSourceBinding | None: ...

    async def get_binding_by_scope(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
    ) -> ManagedDataSourceSourceBinding | None: ...

    async def save_binding(
        self,
        binding: ManagedDataSourceSourceBinding,
    ) -> ManagedDataSourceSourceBinding: ...

    async def delete_binding(self, binding_id: str) -> bool: ...

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
    ) -> DataSourcePage: ...

    async def entitlement_exists(
        self,
        *,
        data_source_id: str,
        status: str | None = None,
        tenant_id: str | None = None,
        scope_type: str | None = None,
        organization_unit_ids: Sequence[str] | None = None,
        exclude_id: str | None = None,
    ) -> bool: ...

    async def get_entitlement(
        self,
        entitlement_id: str,
    ) -> ManagedDataSourceSourceEntitlement | None: ...

    async def get_entitlement_by_scope_source(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
        data_source_id: str,
    ) -> ManagedDataSourceSourceEntitlement | None: ...

    async def save_entitlement(
        self,
        entitlement: ManagedDataSourceSourceEntitlement,
    ) -> ManagedDataSourceSourceEntitlement: ...

    async def save_entitlements(
        self,
        entitlements: Sequence[ManagedDataSourceSourceEntitlement],
    ) -> Sequence[ManagedDataSourceSourceEntitlement]: ...

    async def delete_entitlement(self, entitlement_id: str) -> bool: ...


class ZhizhiDataSourceOrganizationDirectory(Protocol):
    """Zhizhi organization facts required by Data Source hierarchy policy."""

    async def get_tenant(self, tenant_id: str) -> ManagedTenant | None: ...

    async def get_organization_unit(
        self, organization_unit_id: str
    ) -> ManagedOrganizationUnit | None: ...

    async def get_organization_path(
        self, tenant_id: str, organization_unit_id: str
    ) -> tuple[ManagedOrganizationUnit, ...]: ...

    async def descendant_ids(self, organization_unit_ids: Sequence[str]) -> Sequence[str]: ...


class DataSourceCredentialCipher(Protocol):
    """Encrypt and decrypt stored Data Source credential mappings."""

    def encrypt(self, payload: dict[str, Any]) -> str: ...

    def decrypt(self, ciphertext: str) -> dict[str, Any]: ...
