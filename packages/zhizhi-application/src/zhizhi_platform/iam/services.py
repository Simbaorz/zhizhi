"""致知 administrator authentication use cases."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.iam.models import (
    AdminNavigationItem,
    AdminSessionUser,
    AdminUser,
)
from zhizhi_platform.iam.ports import (
    AdminSessionRepository,
    AdminUserRepository,
    IdentitySecurity,
    LoginThrottlePort,
    PasswordTransport,
)

ADMIN_NAVIGATION_ITEMS: tuple[AdminNavigationItem, ...] = (
    AdminNavigationItem(
        key="global",
        label="全局管理",
        path="/global",
        permission_code="",
        super_only=True,
    ),
    AdminNavigationItem(key="org", label="组织管理", path="/org", permission_code="org.view"),
    AdminNavigationItem(
        key="accounts",
        label="账号管理",
        path="/accounts",
        permission_code="",
        permission_codes=("admins.view",),
    ),
    AdminNavigationItem(key="models", label="模型管理", path="/models", permission_code="llm.view"),
    AdminNavigationItem(
        key="scene-git",
        label="场景 Git 授权",
        path="/scene-git",
        permission_code="scene_git.view",
    ),
    AdminNavigationItem(
        key="data-sources",
        label="数据源源",
        path="/data-sources",
        permission_code="data_source.view",
    ),
    AdminNavigationItem(
        key="skills", label="技能管理", path="/skills", permission_code="skills.view"
    ),
    AdminNavigationItem(
        key="scenes", label="业务场景管理", path="/scenes", permission_code="scenes.view"
    ),
)


class AdminLoginBlockedError(Exception):
    """Raised when an administrator is temporarily blocked by throttling."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Admin login is temporarily blocked.")
        self.retry_after_seconds = retry_after_seconds


class AdminAuthService:
    """Handle admin login, session validation, profile, and credentials."""

    def __init__(
        self,
        *,
        user_repository: AdminUserRepository,
        session_repository: AdminSessionRepository,
        identity_security: IdentitySecurity,
        login_throttle: LoginThrottlePort,
        password_transport: PasswordTransport,
    ) -> None:
        self._user_repository = user_repository
        self._session_repository = session_repository
        self._identity_security = identity_security
        self._login_throttle = login_throttle
        self._password_transport = password_transport

    def password_public_key_payload(self) -> dict[str, str]:
        return self._password_transport.public_key_payload()

    def decode_token(self, token: str) -> dict[str, Any]:
        return self._identity_security.decode_admin_token(token)

    async def login(
        self,
        *,
        username: str,
        encrypted_password: str,
        client_ip: str,
    ) -> dict[str, object]:
        decision = await self._login_throttle.check(client_ip, username)
        if decision.blocked:
            raise AdminLoginBlockedError(decision.retry_after_seconds)
        try:
            password = await self._password_transport.decrypt_async(encrypted_password)
            result = await self._login(username, password)
        except ValueError:
            await self._login_throttle.register_failure(client_ip, username)
            raise
        except ApplicationError as exc:
            if exc.kind in {
                ApplicationErrorKind.UNAUTHENTICATED,
                ApplicationErrorKind.FORBIDDEN,
            }:
                await self._login_throttle.register_failure(client_ip, username)
            raise
        await self._login_throttle.register_success(username)
        return result

    async def _login(self, username: str, password: str) -> dict[str, object]:
        user = await self._user_repository.get_by_username(username)
        if user is None or not await self._identity_security.verify_password_async(
            password, user.password_hash
        ):
            raise ApplicationError(ApplicationErrorKind.UNAUTHENTICATED, "用户名或密码错误。")
        if user.status != "active":
            raise ApplicationError(ApplicationErrorKind.FORBIDDEN, "账号已禁用。")
        await self._user_repository.touch_last_login(user.id)
        session_user = await self._session_repository.load_session_user(user)
        return {
            "token": self._identity_security.issue_admin_token(
                user_id=user.id,
                username=user.username,
                is_super=user.is_super,
                token_version=user.token_version,
            ),
            **_admin_session_payload(session_user),
        }

    async def load_session(self, *, user_id: str, token_version: int) -> AdminSessionUser:
        user = await self._user_repository.get_by_id(user_id)
        if user is None or user.status != "active":
            raise ApplicationError(
                ApplicationErrorKind.UNAUTHENTICATED,
                "Admin user does not exist or is inactive.",
            )
        if token_version != user.token_version:
            raise ApplicationError(
                ApplicationErrorKind.UNAUTHENTICATED,
                "Admin token has been revoked.",
            )
        return await self._session_repository.load_session_user(user)

    async def logout(self, session_user: AdminSessionUser) -> None:
        user = await self._require_current_user(session_user)
        await self._user_repository.save(
            user.model_copy(
                update={
                    "token_version": user.token_version + 1,
                    "updated_by_admin_user_id": user.id,
                }
            )
        )

    def me(self, session_user: AdminSessionUser) -> dict[str, object]:
        return {**_admin_session_payload(session_user), "is_super": session_user.is_super}

    async def update_profile(
        self,
        session_user: AdminSessionUser,
        *,
        display_name: str | None,
        phone: str | None,
        email: str | None,
    ) -> dict[str, object]:
        user = await self._require_current_user(session_user)
        next_phone = _normalize_phone(phone) if phone is not None else user.phone
        next_email = _normalize_email(email) if email is not None else user.email
        await self._ensure_unique_contact(user.id, phone=next_phone, email=next_email)
        saved = await self._user_repository.save(
            user.model_copy(
                update={
                    "display_name": (
                        display_name.strip() if display_name is not None else user.display_name
                    ),
                    "phone": next_phone,
                    "email": next_email,
                    "updated_by_admin_user_id": user.id,
                }
            )
        )
        return self.me(await self._session_repository.load_session_user(saved))

    async def change_password(
        self,
        session_user: AdminSessionUser,
        *,
        encrypted_current_password: str,
        encrypted_new_password: str,
    ) -> None:
        current_password = await self._password_transport.decrypt_async(encrypted_current_password)
        new_password = await self._password_transport.decrypt_async(encrypted_new_password)
        user = await self._require_current_user(session_user)
        if not await self._identity_security.verify_password_async(
            current_password, user.password_hash
        ):
            raise ApplicationError(ApplicationErrorKind.FORBIDDEN, "当前密码错误。")
        if not new_password:
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "新密码不能为空。")
        await self._user_repository.save(
            user.model_copy(
                update={
                    "password_hash": await self._identity_security.hash_password_async(
                        new_password
                    ),
                    "token_version": user.token_version + 1,
                    "updated_by_admin_user_id": user.id,
                }
            )
        )

    def navigation(self, session_user: AdminSessionUser) -> list[dict[str, object]]:
        return _visible_navigation(session_user)

    async def _require_current_user(self, session_user: AdminSessionUser) -> AdminUser:
        user = await self._user_repository.get_by_id(session_user.user.id)
        if user is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Admin user does not exist.")
        return user

    async def _ensure_unique_contact(
        self,
        current_user_id: str,
        *,
        phone: str | None,
        email: str | None,
    ) -> None:
        if phone:
            existing = await self._user_repository.get_by_phone(phone)
            if existing is not None and existing.id != current_user_id:
                raise ApplicationError(
                    ApplicationErrorKind.CONFLICT,
                    "手机号已被其他管理员账号使用。",
                )
        if email:
            existing = await self._user_repository.get_by_email(email)
            if existing is not None and existing.id != current_user_id:
                raise ApplicationError(
                    ApplicationErrorKind.CONFLICT,
                    "邮箱已被其他管理员账号使用。",
                )


def _admin_session_payload(session_user: AdminSessionUser) -> dict[str, object]:
    return {
        "user": session_user.user.model_dump(mode="json", exclude={"password_hash"}),
        "roles": [role.model_dump(mode="json") for role in session_user.roles],
        "permissions": [
            permission.model_dump(mode="json") for permission in session_user.permissions
        ],
        "tenant_members": [
            member.model_dump(mode="json") for member in session_user.tenant_members
        ],
        "navigation": _visible_navigation(session_user),
    }


def _visible_navigation(session_user: AdminSessionUser) -> list[dict[str, object]]:
    if session_user.is_super:
        items: Sequence[AdminNavigationItem] = ADMIN_NAVIGATION_ITEMS
    else:
        permission_codes = set(session_user.permission_codes)
        items = tuple(
            item
            for item in ADMIN_NAVIGATION_ITEMS
            if not item.super_only
            and bool(
                set(
                    item.permission_codes
                    or ((item.permission_code,) if item.permission_code else ())
                )
                & permission_codes
            )
        )
    return [item.model_dump(mode="json") for item in items]


def _normalize_phone(phone: str | None) -> str | None:
    normalized = (phone or "").strip()
    return normalized or None


def _normalize_email(email: str | None) -> str | None:
    normalized = (email or "").strip().lower()
    return normalized or None
