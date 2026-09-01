"""Admin APIs for global Git repository resources and availability."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from zhizhi_admin_api.dependencies import AdminSessionDep, GitAdminServiceDep

router = APIRouter(
    prefix="/api/admin/git-repositories",
    tags=["admin", "admin-git-repositories"],
)
PageQuery = Annotated[int, Query(ge=1)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]
SearchQuery = Annotated[str, Query(max_length=128)]


class GitRepositoryCreateRequest(BaseModel):
    """Create one global Git repository resource."""

    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="", max_length=128)
    repo_url: str = Field(min_length=1, max_length=1024)
    default_branch: str = Field(default="", max_length=128)
    username: str = Field(default="", max_length=256)
    password: str = Field(default="", max_length=1024)
    status: Literal["active", "inactive"] = "active"


class GitRepositoryPatchRequest(BaseModel):
    """Update one global Git repository resource."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=128)
    repo_url: str | None = Field(default=None, min_length=1, max_length=1024)
    default_branch: str | None = Field(default=None, max_length=128)
    status: Literal["active", "inactive"] | None = None


class GitRepositoryCredentialsRequest(BaseModel):
    """Replace one global Git repository credential."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(default="", max_length=256)
    password: str = Field(default="", max_length=1024)


class GitEntitlementBatchRequest(BaseModel):
    """Grant several Git repository resources to one tenant."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=64)
    git_repository_ids: list[str] = Field(min_length=1, max_length=20)
    status: Literal["active", "inactive"] = "active"


class GitEntitlementPatchRequest(BaseModel):
    """Enable or disable one Git repository availability entry."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "inactive"]


@router.get("")
async def get_git_repositories(
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
    search: SearchQuery = "",
    status: str = "all",
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict[str, object]:
    """List global Git repository resources."""

    result = await service.list_repositories_for(
        session_user,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "repositories": list(result.items),
        "pagination": {"page": page, "page_size": page_size, "total": result.total},
    }


@router.post("")
async def post_git_repository(
    payload: GitRepositoryCreateRequest,
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
) -> dict[str, object]:
    """Create one global Git repository resource."""

    return await service.create_repository_for(session_user, **payload.model_dump())


@router.patch("/{repository_id}")
async def patch_git_repository(
    repository_id: str,
    payload: GitRepositoryPatchRequest,
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
) -> dict[str, object]:
    """Update one global Git repository resource."""

    return await service.update_repository_for(
        session_user,
        repository_id,
        **payload.model_dump(),
    )


@router.delete("/{repository_id}")
async def remove_git_repository(
    repository_id: str,
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
) -> dict[str, object]:
    """Delete one unused global Git repository resource."""

    return await service.delete_repository_for(session_user, repository_id)


@router.patch("/{repository_id}/credentials")
async def patch_git_repository_credentials(
    repository_id: str,
    payload: GitRepositoryCredentialsRequest,
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
) -> dict[str, object]:
    """Replace or clear one global Git repository credential."""

    return await service.update_credentials_for(
        session_user,
        repository_id,
        **payload.model_dump(),
    )


@router.post("/{repository_id}/test")
async def post_git_repository_test(
    repository_id: str,
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
) -> dict[str, object]:
    """Test one global Git repository resource."""

    return await service.test_repository_for(session_user, repository_id)


@router.get("/entitlements/list")
async def get_git_entitlements(
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
    tenant_id: str = Query(min_length=1),
    search: SearchQuery = "",
    status: str = "all",
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict[str, object]:
    """List Git repository availability entries."""

    result = await service.list_entitlements_for(
        session_user,
        tenant_id,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "entitlements": list(result.items),
        "repositories": list(result.repositories),
        "assignable_repositories": list(result.assignable_repositories),
        "pagination": {"page": page, "page_size": page_size, "total": result.total},
    }


@router.post("/entitlements/batch")
async def post_git_entitlements(
    payload: GitEntitlementBatchRequest,
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
) -> dict[str, object]:
    """Grant several Git resources to one tenant-level availability pool."""

    return {
        "entitlements": await service.create_entitlements_for(
            session_user,
            tenant_id=payload.tenant_id,
            scope_type="tenant",
            organization_unit_id="",
            git_repository_ids=payload.git_repository_ids,
            status=payload.status,
        )
    }


@router.patch("/entitlements/{entitlement_id}")
async def patch_git_entitlement(
    entitlement_id: str,
    payload: GitEntitlementPatchRequest,
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
) -> dict[str, object]:
    """Enable or disable one Git availability entry."""

    return await service.update_entitlement_for(
        session_user,
        entitlement_id,
        status=payload.status,
    )


@router.delete("/entitlements/{entitlement_id}")
async def remove_git_entitlement(
    entitlement_id: str,
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
) -> dict[str, object]:
    """Delete one Git availability entry."""

    return await service.delete_entitlement_for(session_user, entitlement_id)


@router.get("/available/list")
async def get_available_git_repositories(
    session_user: AdminSessionDep,
    service: GitAdminServiceDep,
    tenant_id: str = Query(min_length=1),
) -> dict[str, object]:
    """Return active Git resources available to tenant-level Scene management."""

    return {
        "repositories": await service.list_available_repositories_for(
            session_user,
            tenant_id,
        )
    }
