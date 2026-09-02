"""Admin tenant-member authorization routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from zhizhi_admin_api.dependencies import (
    AdminSessionDep,
    TenantMemberAdminServiceDep,
)
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminScopeType,
    ReplaceTenantMemberAuthorizationCommand,
)

router = APIRouter(prefix="/api/admin/tenant-members", tags=["admin"])
AllowedAdminScopeType = Literal["tenant", "organization_unit"]


class AdminScopePayload(BaseModel):
    """Scope payload for admin APIs."""

    model_config = ConfigDict(extra="forbid")

    scope_type: AllowedAdminScopeType
    scope_tenant_id: str = ""
    scope_organization_unit_id: str = ""

    def to_scope_ref(self) -> AdminScopeRef:
        """Convert the transport payload to a 致知 scope reference."""

        return AdminScopeRef(
            scope_type=AdminScopeType(self.scope_type),
            scope_tenant_id=self.scope_tenant_id,
            scope_organization_unit_id=self.scope_organization_unit_id,
        )


class AdminTenantMemberAuthorizationRequest(BaseModel):
    """Replace roles and data scopes for one bound admin tenant member."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    admin_user_id: str = Field(min_length=1)
    role_ids: list[str] = Field(default_factory=list)
    scope_mode: str = "tenant"
    scopes: list[AdminScopePayload] = Field(default_factory=list)
    status: Literal["active", "inactive"] = "active"

    def to_scope_refs(self) -> tuple[AdminScopeRef, ...]:
        """Return requested data scopes."""

        return tuple(scope.to_scope_ref() for scope in self.scopes)


@router.get("/assignable-roles")
async def list_assignable_roles(
    *,
    session_user: AdminSessionDep,
    service: TenantMemberAdminServiceDep,
) -> dict[str, object]:
    """List roles the current account can assign."""

    return {"roles": await service.list_assignable_roles(session_user)}


@router.post("")
async def replace_tenant_member_authorization(
    payload: AdminTenantMemberAuthorizationRequest,
    session_user: AdminSessionDep,
    service: TenantMemberAdminServiceDep,
) -> dict[str, object]:
    """Replace roles and data scopes for one bound admin tenant member."""

    return await service.replace_authorization(
        session_user,
        ReplaceTenantMemberAuthorizationCommand(
            tenant_id=payload.tenant_id,
            admin_user_id=payload.admin_user_id,
            role_ids=tuple(payload.role_ids),
            scopes=payload.to_scope_refs(),
            status=payload.status,
        ),
    )


@router.delete("/{member_id}")
async def deactivate_tenant_member(
    member_id: str,
    session_user: AdminSessionDep,
    service: TenantMemberAdminServiceDep,
) -> dict[str, object]:
    """Deactivate one admin tenant member."""

    return await service.deactivate_member(session_user, member_id)
