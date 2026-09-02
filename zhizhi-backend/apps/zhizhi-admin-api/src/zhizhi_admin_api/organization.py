"""Admin HTTP routes for tenants and arbitrary-depth organization trees."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from zhizhi_admin_api.dependencies import AdminSessionDep, OrganizationAdminServiceDep
from zhizhi_platform.iam import (
    CreateOrganizationUnitCommand,
    CreateTenantCommand,
    UpdateOrganizationUnitCommand,
    UpdateTenantCommand,
)

router = APIRouter(prefix="/api/admin/org", tags=["organization"])
PageQuery = Annotated[int | None, Query(ge=1)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]
SearchQuery = Annotated[str, Query(max_length=128)]


class _OrgRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TenantCreateRequest(_OrgRequest):
    tenant_code: str = Field(min_length=1)
    tenant_name: str = ""
    status: str = "active"


class TenantUpdateRequest(_OrgRequest):
    tenant_name: str | None = None
    status: str | None = None


class OrganizationUnitCreateRequest(_OrgRequest):
    parent_id: str | None = None
    external_key: str = Field(min_length=1)
    name: str = ""
    unit_type: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    status: str = "active"
    sort_order: int = 0


class OrganizationUnitUpdateRequest(_OrgRequest):
    parent_id: str | None = None
    name: str | None = None
    unit_type: str | None = None
    metadata: dict[str, object] | None = None
    status: str | None = None
    sort_order: int | None = None


@router.get("/tenants")
async def list_tenants(
    session_user: AdminSessionDep,
    service: OrganizationAdminServiceDep,
    page: PageQuery = None,
    page_size: PageSizeQuery = 20,
    search: SearchQuery = "",
    status: str = "all",
) -> dict[str, object]:
    return await service.list_tenants(
        session_user,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
    )


@router.post("/tenants")
async def create_tenant(
    payload: TenantCreateRequest,
    session_user: AdminSessionDep,
    service: OrganizationAdminServiceDep,
) -> dict[str, object]:
    return await service.create_tenant(
        session_user, CreateTenantCommand.model_validate(payload.model_dump())
    )


@router.patch("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    payload: TenantUpdateRequest,
    session_user: AdminSessionDep,
    service: OrganizationAdminServiceDep,
) -> dict[str, object]:
    return await service.update_tenant(
        session_user,
        tenant_id,
        UpdateTenantCommand.model_validate(payload.model_dump()),
    )


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    session_user: AdminSessionDep,
    service: OrganizationAdminServiceDep,
) -> dict[str, object]:
    await service.delete_tenant(session_user, tenant_id)
    return {"ok": True}


@router.get("/tenants/{tenant_id}/organization-units")
async def list_organization_units(
    tenant_id: str,
    session_user: AdminSessionDep,
    service: OrganizationAdminServiceDep,
    page: PageQuery = None,
    page_size: PageSizeQuery = 100,
    search: SearchQuery = "",
    status: str = "all",
) -> dict[str, object]:
    return await service.list_organization_units(
        session_user,
        tenant_id,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
    )


@router.post("/tenants/{tenant_id}/organization-units")
async def create_organization_unit(
    tenant_id: str,
    payload: OrganizationUnitCreateRequest,
    session_user: AdminSessionDep,
    service: OrganizationAdminServiceDep,
) -> dict[str, object]:
    return await service.create_organization_unit(
        session_user,
        tenant_id,
        CreateOrganizationUnitCommand.model_validate(payload.model_dump()),
    )


@router.patch("/organization-units/{organization_unit_id}")
async def update_organization_unit(
    organization_unit_id: str,
    payload: OrganizationUnitUpdateRequest,
    session_user: AdminSessionDep,
    service: OrganizationAdminServiceDep,
) -> dict[str, object]:
    values = payload.model_dump(exclude_unset=True)
    values["parent_id_set"] = "parent_id" in payload.model_fields_set
    return await service.update_organization_unit(
        session_user,
        organization_unit_id,
        UpdateOrganizationUnitCommand.model_validate(values),
    )


@router.delete("/organization-units/{organization_unit_id}")
async def delete_organization_unit(
    organization_unit_id: str,
    session_user: AdminSessionDep,
    service: OrganizationAdminServiceDep,
) -> dict[str, object]:
    await service.delete_organization_unit(session_user, organization_unit_id)
    return {"ok": True}
