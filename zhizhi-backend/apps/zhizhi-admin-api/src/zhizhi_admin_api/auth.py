"""Admin authentication routes with the original 致知 HTTP contract."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from zhizhi_admin_api.dependencies import (
    AdminAuthServiceDep,
    AdminSessionDep,
    clear_admin_session_cookies,
    get_admin_session_cookie_secure,
    set_admin_session_cookies,
)
from zhizhi_platform.iam import AdminLoginBlockedError

router = APIRouter(prefix="/api/admin/auth", tags=["admin"])


class AdminLoginRequest(BaseModel):
    """Admin login request."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1)
    encrypted_password: str = Field(min_length=1)


class AdminLoginResponse(BaseModel):
    """Token-free browser session payload returned after Admin login."""

    model_config = ConfigDict(extra="forbid")

    user: dict[str, object]
    roles: list[dict[str, object]]
    permissions: list[dict[str, object]]
    tenant_members: list[dict[str, object]]
    navigation: list[dict[str, object]]


class AdminProfileUpdateRequest(BaseModel):
    """Current admin profile update request."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    phone: str | None = None
    email: str | None = None


class AdminPasswordChangeRequest(BaseModel):
    """Current admin password change request."""

    model_config = ConfigDict(extra="forbid")

    encrypted_current_password: str = Field(min_length=1)
    encrypted_new_password: str = Field(min_length=1)


@router.get("/password-key")
async def password_key(service: AdminAuthServiceDep) -> dict[str, str]:
    """Return the public key used by browser clients to encrypt passwords."""

    return service.password_public_key_payload()


@router.post("/login", response_model=AdminLoginResponse)
async def login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    service: AdminAuthServiceDep,
) -> AdminLoginResponse:
    """Authenticate one admin account and establish its browser session."""

    client_ip = request.client.host if request.client is not None else "unknown"
    try:
        result = await service.login(
            username=payload.username,
            encrypted_password=payload.encrypted_password,
            client_ip=client_ip,
        )
    except AdminLoginBlockedError as exc:
        raise HTTPException(
            status_code=429,
            detail="登录失败次数过多，请稍后重试。",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid encrypted password.") from exc
    payload_without_token = dict(result)
    token = payload_without_token.pop("token", None)
    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=503, detail="Admin session could not be established.")
    set_admin_session_cookies(
        response,
        token,
        secure=get_admin_session_cookie_secure(request),
    )
    return AdminLoginResponse.model_validate(payload_without_token)


@router.post("/logout")
async def logout(
    response: Response,
    session_user: AdminSessionDep,
    service: AdminAuthServiceDep,
) -> dict[str, object]:
    """Revoke all existing tokens for the current admin account."""

    await service.logout(session_user)
    clear_admin_session_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(
    session_user: AdminSessionDep,
    service: AdminAuthServiceDep,
) -> dict[str, object]:
    """Return current authenticated admin session."""

    return service.me(session_user)


@router.patch("/me/profile")
async def update_profile(
    payload: AdminProfileUpdateRequest,
    session_user: AdminSessionDep,
    service: AdminAuthServiceDep,
) -> dict[str, object]:
    """Update the current admin's editable profile fields."""

    return await service.update_profile(
        session_user,
        display_name=payload.display_name,
        phone=payload.phone,
        email=payload.email,
    )


@router.post("/me/password")
async def change_password(
    payload: AdminPasswordChangeRequest,
    response: Response,
    session_user: AdminSessionDep,
    service: AdminAuthServiceDep,
) -> dict[str, object]:
    """Change the current admin's password."""

    try:
        await service.change_password(
            session_user,
            encrypted_current_password=payload.encrypted_current_password,
            encrypted_new_password=payload.encrypted_new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid encrypted password.") from exc
    clear_admin_session_cookies(response)
    return {"ok": True}


@router.get("/navigation")
async def navigation(
    session_user: AdminSessionDep,
    service: AdminAuthServiceDep,
) -> dict[str, object]:
    """Return visible left navigation items."""

    return {"items": service.navigation(session_user)}
