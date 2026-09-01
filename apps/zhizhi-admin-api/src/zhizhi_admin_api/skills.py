"""Zhizhi Skill asset and managed file-tree routes."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from gewu_core.http.downloads import build_path_download_response
from gewu_core.http.request_limits import (
    buffered_limited_request_body,
    stream_limited_request_file,
)
from zhizhi_admin_api.dependencies import AdminSessionDep, SkillAdminServiceDep
from zhizhi_admin_api.file_errors import AdminFileErrorRoute
from zhizhi_platform.iam import AdminScopeRef, AdminScopeType
from zhizhi_platform.workspace.files import FileVersion

PathQuery = Annotated[str, Query()]
ScopeTenantIdQuery = Annotated[str, Query()]
AllowedAdminScopeType = Literal[AdminScopeType.TENANT]
ScopeTypeQuery = Annotated[AllowedAdminScopeType, Query(...)]


class AdminScopePayload(BaseModel):
    """Scope payload for admin APIs."""

    model_config = ConfigDict(extra="forbid")

    scope_type: AllowedAdminScopeType
    scope_tenant_id: str = ""

    def to_scope_ref(self) -> AdminScopeRef:
        return AdminScopeRef(
            scope_type=self.scope_type,
            scope_tenant_id=self.scope_tenant_id,
        )


class ContentFileWriteRequest(AdminScopePayload):
    """Managed shared file write request."""

    path: str = Field(min_length=1)
    content: str = ""
    expected_version: FileVersion | None = None


class ContentDirectoryCreateRequest(AdminScopePayload):
    """Managed shared directory create request."""

    path: str = Field(min_length=1)


class ContentMoveRequest(AdminScopePayload):
    """Managed shared move request."""

    src_path: str = Field(min_length=1)
    dst_path: str = Field(min_length=1)


class ContentDeleteRequest(AdminScopePayload):
    """Managed shared delete request."""

    path: str = Field(min_length=1)
    recursive: bool = False


class SkillWriteRequest(AdminScopePayload):
    """Managed skill write request."""

    content: str = ""
    name: str = ""
    description: str = ""
    status: Literal["enabled", "disabled"] = "enabled"
    source: Literal["admin"] = "admin"


def skill_scope(
    scope_type: AdminScopeType,
    scope_tenant_id: str,
) -> AdminScopeRef:
    return AdminScopePayload(
        scope_type=scope_type,
        scope_tenant_id=scope_tenant_id,
    ).to_scope_ref()


skills_router = APIRouter(
    prefix="/api/admin/skills",
    tags=["admin"],
    route_class=AdminFileErrorRoute,
)
skill_files_router = APIRouter(
    prefix="/api/admin/skill-files",
    tags=["admin"],
    route_class=AdminFileErrorRoute,
)


@skills_router.get("")
async def list_skills(
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """List Skill asset keys in one tenant scope."""
    return cast(
        dict[str, object],
        await service.list_assets(
            session_user,
            skill_scope(scope_type, scope_tenant_id),
        ),
    )


@skills_router.get("/{skill_asset_key}")
async def get_skill(
    skill_asset_key: str,
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Read one DB-managed Skill asset."""
    return await service.get_asset(
        session_user,
        skill_scope(scope_type, scope_tenant_id),
        skill_asset_key,
    )


@skills_router.post("")
async def create_skill(
    payload: SkillWriteRequest,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
) -> dict[str, object]:
    """Create or update one DB-managed Skill asset."""
    return await service.create_asset(
        session_user,
        payload.to_scope_ref(),
        content=payload.content,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        source=payload.source,
    )


@skills_router.put("/package")
async def create_skill_asset_from_package(
    *,
    scope_type: ScopeTypeQuery,
    name: Annotated[str, Query(min_length=1)],
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
    request: Request,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Create one DB-managed Skill asset from a zip package."""
    async with stream_limited_request_file(
        request,
        service.max_package_bytes,
        prefix="zhizhi-admin-skill-create-",
    ) as package_path:
        return await service.create_asset_from_package(
            session_user,
            skill_scope(scope_type, scope_tenant_id),
            name=name,
            content=package_path,
        )


@skills_router.put("/{skill_asset_key}")
async def put_skill(
    skill_asset_key: str,
    payload: SkillWriteRequest,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
) -> dict[str, object]:
    """Update one DB-managed Skill asset."""
    return await service.update_asset(
        session_user,
        payload.to_scope_ref(),
        skill_asset_key,
        content=payload.content,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        source=payload.source,
    )


@skills_router.put("/{skill_asset_key}/package")
async def upload_skill_asset_package(
    skill_asset_key: str,
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
    request: Request,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Replace one DB-managed Skill asset content directory with a zip package."""
    async with stream_limited_request_file(
        request,
        service.max_package_bytes,
        prefix="zhizhi-admin-skill-replace-",
    ) as package_path:
        return await service.replace_asset_package(
            session_user,
            skill_scope(scope_type, scope_tenant_id),
            skill_asset_key,
            package_path,
        )


@skills_router.delete("/{skill_asset_key}")
async def delete_skill(
    skill_asset_key: str,
    payload: AdminScopePayload,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
) -> dict[str, object]:
    """Delete one DB-managed Skill asset."""
    await service.delete_asset(session_user, payload.to_scope_ref(), skill_asset_key)
    return {"ok": True}


@skill_files_router.get("/entries")
async def list_skill_entries(
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
    scope_tenant_id: ScopeTenantIdQuery = "",
    path: PathQuery = ".skills",
) -> dict[str, object]:
    """List files and directories under the managed skills subtree."""
    return {
        "entries": await service.list_entries(
            session_user,
            skill_scope(scope_type, scope_tenant_id),
            path,
        )
    }


@skill_files_router.get("/file")
async def read_skill_file(
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
    path: PathQuery,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Read one text file under the managed skills subtree."""
    return await service.read_file(
        session_user,
        skill_scope(scope_type, scope_tenant_id),
        path,
    )


@skill_files_router.put("/file")
async def write_skill_file(
    payload: ContentFileWriteRequest,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
) -> dict[str, object]:
    """Create or update one text file under the managed skills subtree."""
    return await service.write_file(
        session_user,
        payload.to_scope_ref(),
        path=payload.path,
        content=payload.content,
        expected_version=payload.expected_version,
    )


@skill_files_router.get(
    "/download",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
)
async def download_skill_path(
    *,
    request: Request,  # noqa
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
    path: PathQuery,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> FileResponse:
    """Download one file or directory under the managed skills subtree."""
    del request
    target_path = await service.resolve_download(
        session_user,
        skill_scope(scope_type, scope_tenant_id),
        path,
    )
    return await build_path_download_response(
        target_path,
        fallback_root_name="skills",
        max_archive_bytes=service.max_package_bytes,
        archive_too_large_detail="Skill package exceeds configured limit.",
    )


@skill_files_router.put("/upload")
async def upload_skill_file(
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
    request: Request,
    path: PathQuery,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Replace one file under skills with raw uploaded bytes."""
    async with buffered_limited_request_body(
        request,
        service.max_upload_file_bytes,
    ) as content:
        return await service.replace_file(
            session_user,
            skill_scope(scope_type, scope_tenant_id),
            path=path,
            content=content,
        )


@skill_files_router.put("/package")
async def upload_skill_package(
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
    request: Request,
    path: PathQuery,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Replace one directory under skills with a zip package."""
    async with stream_limited_request_file(
        request,
        service.max_package_bytes,
        prefix="zhizhi-admin-skill-files-upload-",
    ) as package_path:
        return await service.replace_file_package(
            session_user,
            skill_scope(scope_type, scope_tenant_id),
            path=path,
            content=package_path,
        )


@skill_files_router.post("/directories")
async def create_skill_directory(
    payload: ContentDirectoryCreateRequest,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
) -> dict[str, object]:
    """Create one directory under skills."""
    await service.create_directory(session_user, payload.to_scope_ref(), payload.path)
    return {"ok": True}


@skill_files_router.post("/move")
async def move_skill_path(
    payload: ContentMoveRequest,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
) -> dict[str, object]:
    """Move or rename one file or directory under skills."""
    await service.move_path(
        session_user,
        payload.to_scope_ref(),
        src_path=payload.src_path,
        dst_path=payload.dst_path,
    )
    return {"ok": True}


@skill_files_router.delete("")
async def delete_skill_path(
    payload: ContentDeleteRequest,
    session_user: AdminSessionDep,
    service: SkillAdminServiceDep,
) -> dict[str, object]:
    """Delete one file or directory under skills."""
    await service.delete_path(
        session_user,
        payload.to_scope_ref(),
        path=payload.path,
        recursive=payload.recursive,
    )
    return {"ok": True}


__all__ = [
    "skill_files_router",
    "skills_router",
    "AdminScopePayload",
    "ScopeTenantIdQuery",
    "ScopeTypeQuery",
    "PathQuery",
    "ContentDeleteRequest",
    "ContentDirectoryCreateRequest",
    "ContentFileWriteRequest",
    "ContentMoveRequest",
]
