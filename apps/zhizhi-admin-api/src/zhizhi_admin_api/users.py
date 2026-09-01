"""Admin user management routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from zhizhi_admin_api.dependencies import (
    AdminSessionDep,
    AdminUserAdminServiceDep,
)
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminScopeType,
    CreateOrBindAdminUserCommand,
    ResetAdminPasswordCommand,
    UpdateAdminUserCommand,
)

router = APIRouter(prefix="/api/admin/users", tags=["admin"])
PageQuery = Annotated[int, Query(ge=1)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]
SearchQuery = Annotated[str, Query(max_length=128)]
AllowedAdminScopeType = Literal["tenant", "organization_unit"]


class AdminUserCreateOrBindRequest(BaseModel):
    """Create or bind an admin account inside one authorized scope."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    username: str = Field(min_length=1, max_length=64)
    encrypted_password: str = ""
    display_name: str = ""
    phone: str | None = None
    email: str | None = None
    status: Literal["active", "inactive"] = "active"


class AdminUserUpdateRequest(BaseModel):
    """Admin user patch request."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str | None = None
    scope_type: AllowedAdminScopeType | None = None
    scope_tenant_id: str = ""
    scope_organization_unit_id: str = ""

    @model_validator(mode="before")
    @classmethod
    def reject_username_update(cls, value: object) -> object:
        """Reject attempts to change the immutable admin username."""

        if isinstance(value, dict) and "username" in value:
            raise ValueError("Username cannot be modified.")
        return value

    def to_scope_ref_or_none(self) -> AdminScopeRef | None:
        """Return tenant account-management scope when provided."""

        if self.scope_type is None:
            return None
        return AdminScopeRef(
            scope_type=AdminScopeType(self.scope_type),
            scope_tenant_id=self.scope_tenant_id,
            scope_organization_unit_id=self.scope_organization_unit_id,
        )


class ResetPasswordRequest(BaseModel):
    """Admin user password reset request."""

    model_config = ConfigDict(extra="forbid")

    encrypted_password: str = Field(min_length=1)
    scope_type: AllowedAdminScopeType | None = None
    scope_tenant_id: str = ""
    scope_organization_unit_id: str = ""

    def to_scope_ref_or_none(self) -> AdminScopeRef | None:
        """Return reset authorization scope when provided."""

        if self.scope_type is None:
            return None
        return AdminScopeRef(
            scope_type=AdminScopeType(self.scope_type),
            scope_tenant_id=self.scope_tenant_id,
            scope_organization_unit_id=self.scope_organization_unit_id,
        )


@router.get("/tenant-admins")
async def list_tenant_admins(
    session_user: AdminSessionDep,
    service: AdminUserAdminServiceDep,
    tenant_id: str,
    search: SearchQuery = "",
    status: str = "all",
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict[str, object]:
    """List admin accounts assigned inside one tenant tenant."""

    return await service.list_tenant_admins(
        session_user,
        tenant_id=tenant_id,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("/create-or-bind")
async def create_or_bind_admin_user(
    payload: AdminUserCreateOrBindRequest,
    session_user: AdminSessionDep,
    service: AdminUserAdminServiceDep,
) -> dict[str, object]:
    """Create an admin login identity if needed and bind it to a tenant."""

    try:
        return await service.create_or_bind(
            session_user,
            CreateOrBindAdminUserCommand(
                tenant_id=payload.tenant_id,
                username=payload.username,
                encrypted_password=payload.encrypted_password,
                display_name=payload.display_name,
                phone=payload.phone,
                email=payload.email,
                status=payload.status,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid encrypted password.") from exc


@router.patch("/{user_id}")
async def update_admin_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    session_user: AdminSessionDep,
    service: AdminUserAdminServiceDep,
) -> dict[str, object]:
    """Update one admin account."""

    return await service.update_user(
        session_user,
        user_id,
        UpdateAdminUserCommand(
            display_name=payload.display_name,
            phone=payload.phone,
            email=payload.email,
            status=payload.status,
            scope=payload.to_scope_ref_or_none(),
        ),
    )


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    payload: ResetPasswordRequest,
    session_user: AdminSessionDep,
    service: AdminUserAdminServiceDep,
) -> dict[str, object]:
    """Reset one admin account password."""

    try:
        await service.reset_password(
            session_user,
            user_id,
            ResetAdminPasswordCommand(
                encrypted_password=payload.encrypted_password,
                scope=payload.to_scope_ref_or_none(),
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid encrypted password.") from exc
    return {"ok": True}
