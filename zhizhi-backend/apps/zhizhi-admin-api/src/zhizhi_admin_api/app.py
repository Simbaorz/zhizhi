"""Management-facing 致知 FastAPI process entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from gewu_core.config import BootstrapSettings, load_bootstrap_settings_as
from gewu_core.http import (
    DownloadEgressMiddleware,
    HttpRequestBodyLimitMiddleware,
    UploadIngressMiddleware,
    create_base_http_app,
    create_lifespan,
)
from gewu_core.http.lifecycle import HttpProcessRuntime
from zhizhi_admin_api.auth import router as auth_router
from zhizhi_admin_api.data_source import router as data_source_router
from zhizhi_admin_api.git_repositories import router as git_repositories_router
from zhizhi_admin_api.http_policy import (
    admin_request_body_limit,
    is_admin_download_request,
    is_admin_upload_request,
)
from zhizhi_admin_api.llm import router as llm_router
from zhizhi_admin_api.mutation_audit import AdminMutationAuditMiddleware
from zhizhi_admin_api.organization import router as organization_router
from zhizhi_admin_api.response_security import AdminNoStoreMiddleware
from zhizhi_admin_api.roles import router as roles_router
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.scene_assets import router as scene_assets_router
from zhizhi_admin_api.scene_files import router as scene_files_router
from zhizhi_admin_api.scene_git import router as scene_git_router
from zhizhi_admin_api.scopes import router as scopes_router
from zhizhi_admin_api.settings import AdminApiBootstrapSettings
from zhizhi_admin_api.skills import skill_files_router, skills_router
from zhizhi_admin_api.tenant_members import router as tenant_members_router
from zhizhi_admin_api.users import router as users_router


def create_admin_app(
    *,
    bootstrap: BootstrapSettings | None = None,
    runtime: HttpProcessRuntime | None = None,
) -> FastAPI:
    """Create an app that will compose only management dependencies."""
    resolved_bootstrap = bootstrap or load_bootstrap_settings_as(AdminApiBootstrapSettings)
    resolved_runtime = runtime or ZhizhiAdminApiRuntime(resolved_bootstrap)
    app_ = create_base_http_app(
        create_lifespan(resolved_runtime),
        timezone_name=resolved_bootstrap.timezone,
        title="致知 Admin API",
        description="致知 management service",
        version="0.1.0",
    )
    app_.state.admin_session_cookie_secure = bool(
        getattr(resolved_bootstrap, "admin_session_cookie_secure", False)
    )
    app_.add_middleware(AdminNoStoreMiddleware)
    app_.add_middleware(AdminMutationAuditMiddleware)
    app_.add_middleware(
        HttpRequestBodyLimitMiddleware,
        body_limit_resolver=admin_request_body_limit,
    )
    app_.add_middleware(
        UploadIngressMiddleware,
        request_selector=is_admin_upload_request,
    )
    app_.add_middleware(
        DownloadEgressMiddleware,
        request_selector=is_admin_download_request,
    )
    app_.include_router(auth_router)
    app_.include_router(data_source_router)
    app_.include_router(users_router)
    app_.include_router(git_repositories_router)
    app_.include_router(llm_router)
    app_.include_router(organization_router)
    app_.include_router(roles_router)
    app_.include_router(scopes_router)
    app_.include_router(scene_git_router)
    app_.include_router(scene_files_router)
    app_.include_router(scene_assets_router)
    app_.include_router(tenant_members_router)
    app_.include_router(skill_files_router)
    app_.include_router(skills_router)
    return app_


app = create_admin_app()
