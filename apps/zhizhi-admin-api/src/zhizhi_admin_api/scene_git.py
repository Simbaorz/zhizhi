"""Management Scene Git configuration and synchronization routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from zhizhi_admin_api.dependencies import AdminSessionDep, SceneAdminServiceDep
from zhizhi_admin_api.file_errors import AdminFileErrorRoute
from zhizhi_admin_api.scene_schemas import (
    SCENE_SCOPE_FIELDS,
    SceneGitCreateRequest,
    SceneGitPatchRequest,
    scene_scope,
)
from zhizhi_admin_api.skills import (
    AdminScopePayload,
    ScopeTenantIdQuery,
    ScopeTypeQuery,
)
from zhizhi_platform.scene import CreateGitSceneCommand, UpdateGitSceneConfigCommand

router = APIRouter(
    prefix="/api/admin/scenes",
    tags=["admin"],
    route_class=AdminFileErrorRoute,
)


@router.post("/git")
async def create_git_scene(
    payload: SceneGitCreateRequest,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Create one Git-backed Scene asset."""

    return await service.create_git_asset(
        CreateGitSceneCommand(
            scope=payload.to_scope_ref(),
            session_user=session_user,
            **payload.model_dump(exclude=SCENE_SCOPE_FIELDS),
        )
    )


@router.get("/sync-jobs/{job_id}")
async def get_scene_git_job(
    job_id: str,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Return one sync job."""

    return {"job": await service.get_sync_job(session_user, job_id)}


@router.get("/{scene_asset_key}/git")
async def get_scene_git_config(
    scene_asset_key: str,
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """Return one Git-backed Scene configuration."""

    return await service.get_git_config(
        session_user,
        scene_scope(scope_type, scope_tenant_id),
        scene_asset_key,
    )


@router.patch("/{scene_asset_key}/git")
async def patch_scene_git_config(
    scene_asset_key: str,
    payload: SceneGitPatchRequest,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Patch one Git-backed Scene configuration."""

    return await service.update_git_config(
        UpdateGitSceneConfigCommand(
            scope=payload.to_scope_ref(),
            scene_asset_key=scene_asset_key,
            session_user=session_user,
            **payload.model_dump(exclude=SCENE_SCOPE_FIELDS),
        )
    )


@router.post("/{scene_asset_key}/sync")
async def sync_scene_git(
    scene_asset_key: str,
    payload: AdminScopePayload,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
) -> dict[str, object]:
    """Create and enqueue a manual Scene Git sync job."""

    try:
        return {
            "job": await service.request_sync(
                session_user,
                payload.to_scope_ref(),
                scene_asset_key,
            )
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{scene_asset_key}/sync-jobs")
async def list_scene_git_jobs(
    scene_asset_key: str,
    *,
    scope_type: ScopeTypeQuery,
    session_user: AdminSessionDep,
    service: SceneAdminServiceDep,
    scope_tenant_id: ScopeTenantIdQuery = "",
) -> dict[str, object]:
    """List recent sync jobs for one Scene."""

    return {
        "jobs": await service.list_sync_jobs(
            session_user,
            scene_scope(scope_type, scope_tenant_id),
            scene_asset_key,
        )
    }
