"""致知 Data Source source, entitlement, and binding management routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from zhizhi_admin_api.dependencies import (
    AdminSessionDep,
    DataSourceAdminServiceDep,
)
from zhizhi_platform.data_source import (
    CreateDataSourceBindingCommand,
    CreateDataSourceEntitlementCommand,
    CreateDataSourceSourceCommand,
    UpdateDataSourceSourceCommand,
)

router = APIRouter(prefix="/api/admin/data-sources", tags=["admin"])
PageQuery = Annotated[int, Query(ge=1)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]
SearchQuery = Annotated[str, Query(max_length=128)]


class DataSourceSourceCreateRequest(BaseModel):
    """Data source create request."""

    model_config = ConfigDict(extra="forbid")

    source_key: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    status: str = "active"
    api_url: str = Field(min_length=1)
    app_id: str = Field(min_length=1)
    app_key: str = Field(min_length=1)
    app_secret: str = Field(min_length=1)
    default_database_key: str = Field(min_length=1)
    exec_sources_code: str = Field(min_length=1)
    timeout_seconds: int = 30
    default_max_rows: int = 50
    hard_max_rows: int = 500
    allow_databases: str = ""
    log_sql: bool = False


class DataSourceSourceUpdateRequest(BaseModel):
    """Data source update request."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    description: str | None = None
    status: str | None = None
    api_url: str | None = None
    app_id: str | None = None
    app_key: str | None = None
    app_secret: str | None = None
    default_database_key: str | None = None
    exec_sources_code: str | None = None
    timeout_seconds: int | None = None
    default_max_rows: int | None = None
    hard_max_rows: int | None = None
    allow_databases: str | None = None
    log_sql: bool | None = None


class DataSourceBindingCreateRequest(BaseModel):
    """Data source binding create request."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    scope_type: Literal["tenant", "organization_unit"]
    organization_unit_id: str = ""
    data_source_id: str = Field(min_length=1)
    status: str = "active"


class DataSourceEntitlementCreateRequest(BaseModel):
    """Available data source entry create request."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    scope_type: Literal["tenant", "organization_unit"]
    organization_unit_id: str = ""
    data_source_ids: list[str] = Field(min_length=1, max_length=10)
    status: str = "active"


class DataSourceEntitlementUpdateRequest(BaseModel):
    """Available data source entry update request."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = None


class DataSourceBindingUpdateRequest(BaseModel):
    """Data source binding update request."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = None


@router.get("/sources")
async def list_sources(
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
    search: SearchQuery = "",
    status: str = "all",
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict[str, object]:
    """List data source sources."""

    result = await service.list_sources(
        session_user,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "sources": list(result.items),
        "pagination": {"page": page, "page_size": page_size, "total": result.total},
    }


@router.post("/sources")
async def create_source(
    payload: DataSourceSourceCreateRequest,
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
) -> dict[str, object]:
    """Create one data source source."""

    return await service.create_source(
        session_user,
        CreateDataSourceSourceCommand.model_validate(payload.model_dump()),
    )


@router.patch("/sources/{source_id}")
async def update_source(
    source_id: str,
    payload: DataSourceSourceUpdateRequest,
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
) -> dict[str, object]:
    """Update one data source source."""

    return await service.update_source(
        session_user,
        source_id,
        UpdateDataSourceSourceCommand.model_validate(payload.model_dump()),
    )


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: str,
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
) -> dict[str, object]:
    """Delete one data source source."""

    return await service.delete_source(session_user, source_id)


@router.get("/bindings")
async def list_bindings(
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
    tenant_id: str | None = None,
    scope_type: str = "all",
    organization_unit_id: str = "",
    search: SearchQuery = "",
    status: str = "all",
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict[str, object]:
    """List data source source bindings."""

    result = await service.list_bindings(
        session_user,
        tenant_id=tenant_id,
        scope_type=scope_type,
        organization_unit_id=organization_unit_id,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "bindings": list(result.items),
        "pagination": {"page": page, "page_size": page_size, "total": result.total},
    }


@router.get("/entitlements")
async def list_entitlements(
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
    tenant_id: str | None = None,
    scope_type: str = "all",
    organization_unit_id: str = "",
    search: str = "",
    status: str = "all",
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict[str, object]:
    """List available data sources for organization scopes."""

    result = await service.list_entitlements(
        session_user,
        tenant_id=tenant_id,
        scope_type=scope_type,
        organization_unit_id=organization_unit_id,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "entitlements": list(result.items),
        "pagination": {"page": page, "page_size": page_size, "total": result.total},
    }


@router.post("/entitlements")
async def create_entitlement(
    payload: DataSourceEntitlementCreateRequest,
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
) -> dict[str, object]:
    """Make data sources available to one organization scope."""

    return await service.create_entitlement(
        CreateDataSourceEntitlementCommand.model_validate(payload.model_dump()),
        session_user,
    )


@router.patch("/entitlements/{entitlement_id}")
async def update_entitlement(
    entitlement_id: str,
    payload: DataSourceEntitlementUpdateRequest,
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
) -> dict[str, object]:
    """Update one available data source entry."""

    return await service.update_entitlement(
        entitlement_id,
        status=payload.status,
        session_user=session_user,
    )


@router.delete("/entitlements/{entitlement_id}")
async def delete_entitlement(
    entitlement_id: str,
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
) -> dict[str, object]:
    """Delete one available data source entry."""

    return await service.delete_entitlement(entitlement_id, session_user)


@router.post("/bindings")
async def create_binding(
    payload: DataSourceBindingCreateRequest,
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
) -> dict[str, object]:
    """Create one data source source binding."""

    return await service.create_binding(
        CreateDataSourceBindingCommand.model_validate(payload.model_dump()),
        session_user,
    )


@router.patch("/bindings/{binding_id}")
async def update_binding(
    binding_id: str,
    payload: DataSourceBindingUpdateRequest,
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
) -> dict[str, object]:
    """Update one data source source binding."""

    return await service.update_binding(
        binding_id,
        status=payload.status,
        session_user=session_user,
    )


@router.delete("/bindings/{binding_id}")
async def delete_binding(
    binding_id: str,
    session_user: AdminSessionDep,
    service: DataSourceAdminServiceDep,
) -> dict[str, object]:
    """Delete one data source source binding."""

    return await service.delete_binding(binding_id, session_user)
