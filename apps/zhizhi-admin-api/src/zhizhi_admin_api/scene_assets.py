"""致知 management Scene asset routes."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Query, Request

from gewu_core.http.request_limits import stream_limited_request_file
from zhizhi_admin_api.dependencies import AdminSessionDep, SceneAdminServiceDep
from zhizhi_admin_api.file_errors import AdminFileErrorRoute
from zhizhi_admin_api.scene_schemas import (
    ScenePatchRequest,
    SceneWriteRequest,
    scene_scope,
)
from zhizhi_admin_api.skills import (
    AdminScopePayload,
    ScopeTenantIdQuery,
    ScopeTypeQuery,
)

router = APIRouter(
    prefix="/api/admin/scenes",
    tags=["admin"],
    route_class=AdminFileErrorRoute,
)


@router.get("")
async def list_scenes(
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """List tenant-level Scene assets."""

    return {
        "scenes": cast(
            list[dict[str, object]],
            await service.list_assets(
                session_user,
                scene_scope(scope_type, scope_tenant_id),
            ),
        )
    }


@router.post("")
async def create_scene(
    payload: SceneWriteRequest,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Create or replace one tenant-level Scene asset."""

    return await service.create_asset(
        session_user,
        payload.to_scope_ref(),
        name=payload.name,
        description=payload.description,
        status=payload.status,
        source=payload.source,
        required_skill_asset_key=payload.required_skill_asset_key,
        recommended_skill_asset_keys=payload.recommended_skill_asset_keys,
    )


@router.put("/package")
async def create_scene_asset_from_package(
    *,
    scope_type: ScopeTypeQuery,
    name: Annotated[str, Query(min_length=1)],
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
    request: Request,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Create one DB-managed Scene asset from a zip package."""

    async with stream_limited_request_file(
        request,
        service.max_package_bytes,
        prefix="zhizhi-admin-scene-create-",
    ) as package_path:
        return await service.create_asset_from_package(
            session_user,
            scene_scope(scope_type, scope_tenant_id),
            name=name,
            content=package_path,
        )


@router.patch("/{scene_asset_key}")
async def patch_scene(
    scene_asset_key: str,
    payload: ScenePatchRequest,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Patch one tenant-level Scene asset."""

    return await service.update_asset(
        session_user,
        payload.to_scope_ref(),
        scene_asset_key,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        source=payload.source,
        required_skill_asset_key=payload.required_skill_asset_key,
        recommended_skill_asset_keys=payload.recommended_skill_asset_keys,
    )


@router.put("/{scene_asset_key}/package")
async def upload_scene_package(
    scene_asset_key: str,
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
    request: Request,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Replace one Scene asset content directory with a zip package."""

    async with stream_limited_request_file(
        request,
        service.max_package_bytes,
        prefix="zhizhi-admin-scene-replace-",
    ) as package_path:
        return await service.replace_asset_package(
            session_user,
            scene_scope(scope_type, scope_tenant_id),
            scene_asset_key,
            package_path,
        )


@router.delete("/{scene_asset_key}")
async def delete_scene(
    scene_asset_key: str,
    payload: AdminScopePayload,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Delete one tenant-level Scene asset."""

    await service.delete_asset(session_user, payload.to_scope_ref(), scene_asset_key)
    return {"ok": True}
