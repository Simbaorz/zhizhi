"""Admin role and permission routes with the original Zhizhi HTTP contract."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from zhizhi_admin_api.dependencies import AdminSessionDep, RoleAdminServiceDep
from zhizhi_platform.iam import CreateRoleCommand, UpdateRoleCommand

router = APIRouter(prefix="/api/admin", tags=["admin"])
PageQuery = Annotated[int, Query(ge=1)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]
SearchQuery = Annotated[str, Query(max_length=128)]


class RoleCreateRequest(BaseModel):
    """Role create request."""

    model_config = ConfigDict(extra="forbid")

    role_code: str = Field(min_length=1)
    role_name: str = Field(min_length=1)
    description: str = ""
    status: Literal["active", "inactive"] = "active"
    is_delegable: bool = True


class RoleUpdateRequest(BaseModel):
    """Role patch request."""

    model_config = ConfigDict(extra="forbid")

    role_name: str | None = None
    description: str | None = None
    status: Literal["active", "inactive"] | None = None
    is_delegable: bool | None = None


class ReplaceRolePermissionsRequest(BaseModel):
    """Replace permissions request."""

    model_config = ConfigDict(extra="forbid")

    permission_ids: list[str] = Field(default_factory=list)


@router.get("/roles")
async def list_roles(
    session_user: AdminSessionDep,
    service: RoleAdminServiceDep,
    search: SearchQuery = "",
    status: str = "all",
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict[str, object]:
    """List roles."""

    return await service.list_roles(
        session_user,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("/roles")
async def create_role(
    payload: RoleCreateRequest,
    session_user: AdminSessionDep,
    service: RoleAdminServiceDep,
) -> dict[str, object]:
    """Create one role."""

    return await service.create_role(
        session_user,
        CreateRoleCommand(
            role_code=payload.role_code,
            role_name=payload.role_name,
            description=payload.description,
            status=payload.status,
            is_delegable=payload.is_delegable,
        ),
    )


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: str,
    payload: RoleUpdateRequest,
    session_user: AdminSessionDep,
    service: RoleAdminServiceDep,
) -> dict[str, object]:
    """Update one role."""

    return await service.update_role(
        session_user,
        role_id,
        UpdateRoleCommand(
            role_name=payload.role_name,
            description=payload.description,
            status=payload.status,
            is_delegable=payload.is_delegable,
        ),
    )


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: str,
    session_user: AdminSessionDep,
    service: RoleAdminServiceDep,
) -> dict[str, object]:
    """Delete one role."""

    await service.delete_role(session_user, role_id)
    return {"ok": True}


@router.get("/roles/{role_id}/permissions")
async def list_role_permissions(
    role_id: str,
    session_user: AdminSessionDep,
    service: RoleAdminServiceDep,
) -> dict[str, object]:
    """List one role's permissions."""

    return {"permissions": await service.list_role_permissions(session_user, role_id)}


@router.put("/roles/{role_id}/permissions")
async def replace_role_permissions(
    role_id: str,
    payload: ReplaceRolePermissionsRequest,
    session_user: AdminSessionDep,
    service: RoleAdminServiceDep,
) -> dict[str, object]:
    """Replace one role's permissions."""

    await service.replace_role_permissions(session_user, role_id, payload.permission_ids)
    return {"ok": True}


@router.get("/permissions")
async def list_permissions(
    session_user: AdminSessionDep,
    service: RoleAdminServiceDep,
) -> dict[str, object]:
    """List all permissions."""

    return {"permissions": await service.list_permissions(session_user)}
