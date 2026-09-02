"""Administrator Cookie-session authentication dependencies."""

from __future__ import annotations

import hmac
import secrets
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request, Response, Security
from fastapi.security import APIKeyCookie

from gewu_core.errors import ApplicationError
from gewu_core.http.application_errors import application_error_status_code
from zhizhi_admin_api.mutation_audit import attach_admin_audit_context
from zhizhi_admin_api.shared_asset_admin import ZhizhiAssetAdminService
from zhizhi_platform.audit import AdminAuditActor, AdminAuditWriter
from zhizhi_platform.data_source import ZhizhiDataSourceAdminService
from zhizhi_platform.git import ZhizhiGitAdminService
from zhizhi_platform.iam import (
    AdminAuthService,
    AdminSessionUser,
    AdminUserAdminService,
    OrganizationAdminService,
    RoleAdminService,
    TenantMemberAdminService,
)
from zhizhi_platform.llm import ZhizhiLLMAdminService

ADMIN_SESSION_COOKIE = "zhizhi_admin_session"
ADMIN_CSRF_COOKIE = "zhizhi_admin_csrf"
ADMIN_CSRF_HEADER = "X-CSRF-Token"
ADMIN_SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_admin_session_cookie_scheme = APIKeyCookie(
    name=ADMIN_SESSION_COOKIE,
    scheme_name="AdminSessionCookie",
    description="HttpOnly Admin session Cookie established by the login endpoint.",
    auto_error=False,
)
AdminSessionCookie = Annotated[str | None, Security(_admin_session_cookie_scheme)]
AdminCsrfHeader = Annotated[
    str | None,
    Header(
        alias=ADMIN_CSRF_HEADER,
        description="Required for authenticated POST, PUT, PATCH, and DELETE requests.",
    ),
]


def get_admin_auth_service(request: Request) -> AdminAuthService:
    service = getattr(getattr(request.app.state, "runtime", None), "auth_service", None)
    if not isinstance(service, AdminAuthService):
        raise HTTPException(status_code=503, detail="Admin auth service is not configured.")
    return service


AdminAuthServiceDep = Annotated[AdminAuthService, Depends(get_admin_auth_service)]


def get_admin_user_admin_service(request: Request) -> AdminUserAdminService:
    service = getattr(getattr(request.app.state, "runtime", None), "admin_user_service", None)
    if not isinstance(service, AdminUserAdminService):
        raise HTTPException(
            status_code=503,
            detail="Admin user management service is not configured.",
        )
    return service


AdminUserAdminServiceDep = Annotated[
    AdminUserAdminService,
    Depends(get_admin_user_admin_service),
]


def get_role_admin_service(request: Request) -> RoleAdminService:
    service = getattr(getattr(request.app.state, "runtime", None), "role_service", None)
    if not isinstance(service, RoleAdminService):
        raise HTTPException(status_code=503, detail="Role management service is not configured.")
    return service


RoleAdminServiceDep = Annotated[RoleAdminService, Depends(get_role_admin_service)]


def get_organization_admin_service(request: Request) -> OrganizationAdminService:
    service = getattr(
        getattr(request.app.state, "runtime", None),
        "organization_service",
        None,
    )
    if not isinstance(service, OrganizationAdminService):
        raise HTTPException(status_code=503, detail="Organization service is not configured.")
    return service


OrganizationAdminServiceDep = Annotated[
    OrganizationAdminService,
    Depends(get_organization_admin_service),
]


def get_tenant_member_admin_service(request: Request) -> TenantMemberAdminService:
    service = getattr(
        getattr(request.app.state, "runtime", None),
        "tenant_member_service",
        None,
    )
    if not isinstance(service, TenantMemberAdminService):
        raise HTTPException(
            status_code=503,
            detail="Tenant member management service is not configured.",
        )
    return service


TenantMemberAdminServiceDep = Annotated[
    TenantMemberAdminService,
    Depends(get_tenant_member_admin_service),
]


def get_git_admin_service(request: Request) -> ZhizhiGitAdminService:
    service = getattr(getattr(request.app.state, "runtime", None), "git_service", None)
    if not isinstance(service, ZhizhiGitAdminService):
        raise HTTPException(status_code=503, detail="Git management service is not configured.")
    return service


GitAdminServiceDep = Annotated[ZhizhiGitAdminService, Depends(get_git_admin_service)]


def get_llm_admin_service(request: Request) -> ZhizhiLLMAdminService:
    service = getattr(getattr(request.app.state, "runtime", None), "llm_service", None)
    if not isinstance(service, ZhizhiLLMAdminService):
        raise HTTPException(status_code=503, detail="LLM management service is not configured.")
    return service


LLMAdminServiceDep = Annotated[ZhizhiLLMAdminService, Depends(get_llm_admin_service)]


def get_data_source_admin_service(request: Request) -> ZhizhiDataSourceAdminService:
    service = getattr(
        getattr(request.app.state, "runtime", None),
        "data_source_service",
        None,
    )
    if not isinstance(service, ZhizhiDataSourceAdminService):
        raise HTTPException(
            status_code=503,
            detail="Data source management service is not configured.",
        )
    return service


DataSourceAdminServiceDep = Annotated[
    ZhizhiDataSourceAdminService,
    Depends(get_data_source_admin_service),
]


def get_skill_admin_service(request: Request) -> ZhizhiAssetAdminService:
    service = getattr(getattr(request.app.state, "runtime", None), "skill_service", None)
    if not isinstance(service, ZhizhiAssetAdminService) or service.kind != "skill":
        raise HTTPException(status_code=503, detail="Skill management service is not configured.")
    return service


SkillAdminServiceDep = Annotated[
    ZhizhiAssetAdminService,
    Depends(get_skill_admin_service),
]


def get_scene_admin_service(request: Request) -> ZhizhiAssetAdminService:
    service = getattr(getattr(request.app.state, "runtime", None), "scene_service", None)
    if not isinstance(service, ZhizhiAssetAdminService) or service.kind != "scene":
        raise HTTPException(status_code=503, detail="Scene management service is not configured.")
    return service


SceneAdminServiceDep = Annotated[
    ZhizhiAssetAdminService,
    Depends(get_scene_admin_service),
]


async def get_current_admin_session(
    request: Request,
    service: AdminAuthServiceDep,
    session_token: AdminSessionCookie = None,
    csrf_token: AdminCsrfHeader = None,
) -> AdminSessionUser:
    if not session_token:
        raise _unauthorized()
    try:
        payload = service.decode_token(session_token)
    except (jwt.InvalidTokenError, TypeError, ValueError) as exc:
        raise _unauthorized() from exc
    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        raise _unauthorized()
    token_version = payload.get("ver")
    if not isinstance(token_version, int) or isinstance(token_version, bool):
        raise _unauthorized()
    try:
        session = await service.load_session(user_id=user_id, token_version=token_version)
    except ApplicationError as exc:
        raise HTTPException(
            status_code=application_error_status_code(exc),
            detail=exc.detail,
        ) from exc
    _require_admin_csrf(request, csrf_token)
    writer = getattr(getattr(request.app.state, "runtime", None), "audit_writer", None)
    if isinstance(writer, AdminAuditWriter):
        attach_admin_audit_context(
            request,
            actor=AdminAuditActor(
                admin_user_id=session.user.id,
                is_super=session.is_super,
            ),
            writer=writer,
        )
    return session


def set_admin_session_cookies(
    response: Response,
    token: str,
    *,
    secure: bool,
) -> None:
    """Set the HttpOnly admin session and double-submit CSRF cookies."""
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=token,
        max_age=ADMIN_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/admin",
    )
    response.set_cookie(
        key=ADMIN_CSRF_COOKIE,
        value=secrets.token_urlsafe(32),
        max_age=ADMIN_SESSION_MAX_AGE_SECONDS,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def get_admin_session_cookie_secure(request: Request) -> bool:
    secure = getattr(request.app.state, "admin_session_cookie_secure", None)
    if not isinstance(secure, bool):
        raise HTTPException(status_code=503, detail="Admin Cookie policy is not configured.")
    return secure


def clear_admin_session_cookies(response: Response) -> None:
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/api/admin")
    response.delete_cookie(ADMIN_CSRF_COOKIE, path="/")


def _require_admin_csrf(request: Request, supplied: str | None = None) -> None:
    if request.method in SAFE_METHODS:
        return
    expected = request.cookies.get(ADMIN_CSRF_COOKIE, "")
    supplied = supplied or request.headers.get(ADMIN_CSRF_HEADER, "")
    try:
        matches = bool(expected and supplied) and hmac.compare_digest(
            expected.encode("ascii"),
            supplied.encode("ascii"),
        )
    except UnicodeEncodeError:
        matches = False
    if not matches:
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Admin session is missing, expired, or revoked.",
    )


AdminSessionDep = Annotated[AdminSessionUser, Depends(get_current_admin_session)]
