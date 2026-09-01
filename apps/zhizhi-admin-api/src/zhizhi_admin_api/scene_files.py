"""Zhizhi management Scene file-tree routes."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from gewu_core.http.downloads import build_path_download_response
from gewu_core.http.request_limits import (
    buffered_limited_request_body,
    stream_limited_request_file,
)
from zhizhi_admin_api.dependencies import AdminSessionDep, SceneAdminServiceDep
from zhizhi_admin_api.file_errors import AdminFileErrorRoute
from zhizhi_admin_api.scene_schemas import (
    SceneContentDeleteRequest,
    SceneContentDirectoryCreateRequest,
    SceneContentFileWriteRequest,
    SceneContentMoveRequest,
    scene_scope,
)
from zhizhi_admin_api.skills import (
    PathQuery,
    ScopeTenantIdQuery,
    ScopeTypeQuery,
)

router = APIRouter(
    prefix="/api/admin/scenes",
    tags=["admin"],
    route_class=AdminFileErrorRoute,
)


@router.get("/entries")
async def list_scene_entries(
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
    scene_id: str = Query(...),
    path: PathQuery = "",
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """List content entries under one Scene asset."""

    return {
        "entries": await service.list_entries(
            session_user,
            scene_scope(scope_type, scope_tenant_id),
            scene_id=scene_id,
            path=path,
        )
    }


@router.get("/file")
async def read_scene_file(
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
    scene_id: str = Query(...),
    path: PathQuery,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Read one text file under one Scene asset."""

    return await service.read_file(
        session_user,
        scene_scope(scope_type, scope_tenant_id),
        scene_id=scene_id,
        path=path,
    )


@router.put("/file")
async def write_scene_file(
    payload: SceneContentFileWriteRequest,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Create or update one text file under one Scene asset."""

    return await service.write_file(
        session_user,
        payload.to_scope_ref(),
        scene_id=payload.scene_id,
        path=payload.path,
        content=payload.content,
        expected_version=payload.expected_version,
    )


@router.get(
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
async def download_scene_path(
    *,
    request: Request,  # noqa
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
    scene_id: str = Query(...),
    path: PathQuery = "",
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> FileResponse:
    """Download one file or directory under one Scene asset."""

    del request
    target = await service.resolve_download(
        session_user,
        scene_scope(scope_type, scope_tenant_id),
        scene_id=scene_id,
        path=path,
    )
    return await build_path_download_response(
        target,
        fallback_root_name="scene",
        max_archive_bytes=service.max_package_bytes,
        archive_too_large_detail="Scene package exceeds configured limit.",
    )


@router.put("/upload")
async def upload_scene_file(
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
    request: Request,
    scene_id: str = Query(...),
    path: PathQuery,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Replace one file under one Scene with raw uploaded bytes."""

    async with buffered_limited_request_body(request, service.max_upload_file_bytes) as content:
        return await service.replace_file(
            session_user,
            scene_scope(scope_type, scope_tenant_id),
            scene_id=scene_id,
            path=path,
            content=content,
        )


@router.put("/directory-package")
async def upload_scene_directory_package(
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
    request: Request,
    scene_id: str = Query(...),
    path: PathQuery = "",
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Replace one directory under one Scene with a zip package."""

    async with stream_limited_request_file(
        request,
        service.max_package_bytes,
        prefix="zhizhi-admin-scene-directory-",
    ) as package_path:
        return await service.replace_directory_package(
            session_user,
            scene_scope(scope_type, scope_tenant_id),
            scene_id=scene_id,
            path=path,
            content=package_path,
        )


@router.post("/directories")
async def create_scene_directory(
    payload: SceneContentDirectoryCreateRequest,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Create one directory under one Scene asset."""

    await service.create_directory(
        session_user,
        payload.to_scope_ref(),
        scene_id=payload.scene_id,
        path=payload.path,
    )
    return {"ok": True}


@router.post("/move")
async def move_scene_file_path(
    payload: SceneContentMoveRequest,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Move or rename one path under one Scene asset."""

    await service.move_path(
        session_user,
        payload.to_scope_ref(),
        scene_id=payload.scene_id,
        src_path=payload.src_path,
        dst_path=payload.dst_path,
    )
    return {"ok": True}


@router.delete("/path")
async def delete_scene_file_path(
    payload: SceneContentDeleteRequest,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Delete one file or directory under one Scene asset."""

    await service.delete_path(
        session_user,
        payload.to_scope_ref(),
        scene_id=payload.scene_id,
        path=payload.path,
        recursive=payload.recursive,
    )
    return {"ok": True}
