"""Zhizhi tenant-scoped administrator identity management."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.ids import new_entity_id
from zhizhi_platform.audit import AdminAuditActor, AdminAuditWriter
from zhizhi_platform.iam.authorization import ensure_can_manage_admin_member
from zhizhi_platform.iam.codes import canonical_stable_code
from zhizhi_platform.iam.models import (
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
    AdminTenantMember,
    AdminTenantScope,
    AdminUser,
    scope_contains,
)
from zhizhi_platform.iam.ports import (
    AdminOrgReadRepository,
    AdminTenantMemberRepository,
    AdminUserRepository,
    IdentitySecurity,
    PasswordTransport,
)
from zhizhi_platform.iam.tenant_member_service import (
    bind_admin_tenant_member,
    tenant_member_payload,
)


class CreateOrBindAdminUserCommand(BaseModel):
    """Admin identity and initial tenant binding requested by management."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    username: str
    encrypted_password: str
    display_name: str
    phone: str | None
    email: str | None
    status: str


class UpdateAdminUserCommand(BaseModel):
    """Editable identity and tenant-member state for one admin account."""

    model_config = ConfigDict(frozen=True)

    display_name: str | None
    phone: str | None
    email: str | None
    status: str | None
    scope: AdminScopeRef | None


class ResetAdminPasswordCommand(BaseModel):
    """Encrypted password and authorization scope for an admin reset."""

    model_config = ConfigDict(frozen=True)

    encrypted_password: str
    scope: AdminScopeRef | None


class TenantAdminUserPage(BaseModel):
    """One projected page returned by the tenant administrator use case."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, object], ...]
    total: int


class AdminUserAdminService:
    """Handle admin identity and tenant binding operations with auditing."""

    def __init__(
        self,
        *,
        user_repository: AdminUserRepository,
        member_repository: AdminTenantMemberRepository,
        org_repository: AdminOrgReadRepository,
        audit_writer: AdminAuditWriter,
        identity_security: IdentitySecurity,
        password_transport: PasswordTransport,
    ) -> None:
        self._user_repository = user_repository
        self._member_repository = member_repository
        self._org_repository = org_repository
        self._audit_writer = audit_writer
        self._identity_security = identity_security
        self._password_transport = password_transport

    async def list_tenant_admins(
        self,
        session_user: AdminSessionUser,
        *,
        tenant_id: str,
        search: str,
        status: str,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        """Return one filtered page of admin accounts assigned to a tenant."""

        result = await list_tenant_admin_users(
            tenant_id,
            session_user=session_user,
            member_repository=self._member_repository,
            search=search,
            status=status,
            page=page,
            page_size=page_size,
        )
        return {
            "users": list(result.items),
            "pagination": {"page": page, "page_size": page_size, "total": result.total},
        }

    async def create_or_bind(
        self,
        session_user: AdminSessionUser,
        command: CreateOrBindAdminUserCommand,
    ) -> dict[str, object]:
        """Create or reuse an admin identity and bind it to one tenant."""

        tenant_scope = await self._org_repository.hydrate_scope(
            AdminScopeRef(
                scope_type=AdminScopeType.TENANT,
                scope_tenant_id=command.tenant_id,
            )
        )
        _require_scoped_permission(session_user, "admins.create", tenant_scope)
        user = await self._user_repository.get_by_username(command.username)
        identity_action = "reused"
        member: dict[str, object] | None = None
        if user is None:
            if not command.encrypted_password:
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "New admin accounts must include a password.",
                )
            created, member = await create_admin_user_with_tenant_member(
                tenant_id=command.tenant_id,
                username=command.username,
                password=await self._password_transport.decrypt_async(command.encrypted_password),
                display_name=command.display_name,
                phone=command.phone,
                email=command.email,
                status=command.status,
                created_source="super_admin" if session_user.is_super else "tenant_admin",
                session_user=session_user,
                user_repository=self._user_repository,
                member_repository=self._member_repository,
                identity_security=self._identity_security,
            )
            principal_admin_user_id = str(created["id"])
            identity_action = "created"
            await self._audit_writer.write(
                actor=_admin_audit_actor(session_user),
                action="admin_identity.create",
                target_resource_type="zhizhi_admin_user",
                target_resource_id=principal_admin_user_id,
                target_tenant_id=tenant_scope.scope_tenant_id,
                scope_summary=tenant_scope.model_dump(mode="json"),
                after_summary=_admin_user_audit_summary(created),
            )
        else:
            if user.is_super:
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "Super admin accounts cannot be bound to tenants.",
                )
            ensure_admin_identity_contact_matches(
                user,
                phone=command.phone,
                email=command.email,
            )
            principal_admin_user_id = user.id
            await self._audit_writer.write(
                actor=_admin_audit_actor(session_user),
                action="admin_identity.reuse",
                target_resource_type="zhizhi_admin_user",
                target_resource_id=principal_admin_user_id,
                target_tenant_id=tenant_scope.scope_tenant_id,
                scope_summary=tenant_scope.model_dump(mode="json"),
                after_summary=_admin_user_audit_summary(
                    user.model_dump(mode="json", exclude={"password_hash"})
                ),
            )
        if member is None:
            member = await bind_admin_tenant_member(
                tenant_id=command.tenant_id,
                admin_user_id=principal_admin_user_id,
                status=command.status,
                session_user=session_user,
                member_repository=self._member_repository,
                user_repository=self._user_repository,
                org_repository=self._org_repository,
            )
        await self._audit_writer.write(
            actor=_admin_audit_actor(session_user),
            action="admin_tenant_member.bind",
            target_resource_type="zhizhi_admin_tenant_member",
            target_resource_id=str(member["id"]),
            target_tenant_id=tenant_scope.scope_tenant_id,
            scope_summary={
                "scope_mode": member.get("scope_mode"),
                "scopes": member.get("scopes", []),
            },
            after_summary=member,
        )
        return {**member, "identity_action": identity_action}

    async def update_user(
        self,
        session_user: AdminSessionUser,
        user_id: str,
        command: UpdateAdminUserCommand,
    ) -> dict[str, object]:
        """Update one admin identity and its tenant member status."""

        if command.scope is None:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Admin account scope is required.",
            )
        hydrated_scope = await self._org_repository.hydrate_scope(command.scope)
        before_user = await self._user_repository.get_by_id(user_id)
        before_summary = (
            _admin_user_audit_summary(
                before_user.model_dump(mode="json", exclude={"password_hash"})
            )
            if before_user is not None
            else {}
        )
        updated = await update_tenant_admin_user(
            user_id,
            display_name=command.display_name,
            phone=command.phone,
            email=command.email,
            status=command.status,
            session_user=session_user,
            scope=hydrated_scope,
            user_repository=self._user_repository,
            member_repository=self._member_repository,
            actor_admin_user_id=session_user.user.id,
        )
        await self._audit_writer.write(
            actor=_admin_audit_actor(session_user),
            action="admin_identity.update",
            target_resource_type="zhizhi_admin_user",
            target_resource_id=user_id,
            target_tenant_id=hydrated_scope.scope_tenant_id,
            scope_summary=hydrated_scope.model_dump(mode="json"),
            before_summary=before_summary,
            after_summary=_admin_user_audit_summary(updated),
        )
        return updated

    async def reset_password(
        self,
        session_user: AdminSessionUser,
        user_id: str,
        command: ResetAdminPasswordCommand,
    ) -> None:
        """Reset one admin password within an explicitly authorized scope."""

        if command.scope is None:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Admin reset password scope is required.",
            )
        hydrated_scope = await self._org_repository.hydrate_scope(command.scope)
        await ensure_admin_password_reset_scope(
            target_admin_user_id=user_id,
            session_user=session_user,
            scope=hydrated_scope,
            member_repository=self._member_repository,
        )
        await reset_admin_user_password(
            user_id,
            await self._password_transport.decrypt_async(command.encrypted_password),
            self._user_repository,
            identity_security=self._identity_security,
            actor_admin_user_id=session_user.user.id,
        )
        await self._audit_writer.write(
            actor=_admin_audit_actor(session_user),
            action="admin_identity.reset_password",
            target_resource_type="zhizhi_admin_user",
            target_resource_id=user_id,
            target_tenant_id=hydrated_scope.scope_tenant_id,
            scope_summary=hydrated_scope.model_dump(mode="json"),
        )


async def list_tenant_admin_users(
    tenant_id: str,
    *,
    session_user: AdminSessionUser,
    member_repository: AdminTenantMemberRepository,
    search: str = "",
    status: str = "all",
    page: int = 1,
    page_size: int = 20,
) -> TenantAdminUserPage:
    """Return one SQL-filtered page of administrators inside one tenant."""

    tenant_scope = AdminScopeRef(
        scope_type=AdminScopeType.TENANT,
        scope_tenant_id=tenant_id,
    )
    _require_scoped_permission(session_user, "admins.view", tenant_scope)
    result = await member_repository.list_admins_page(
        tenant_id,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
    )
    items: list[dict[str, object]] = []
    for row in result.items:
        user = row.user
        member = row.member
        tenant_admin_status = (
            "active" if user.status == "active" and member.is_active else "inactive"
        )
        roles = _tenant_admin_roles(member)
        items.append(
            {
                **user.model_dump(mode="json", exclude={"password_hash"}),
                "tenant_member_id": member.id,
                "tenant_id": tenant_id,
                "tenant_admin_status": tenant_admin_status,
                "scope_mode": str(member.scope_mode),
                "role_count": len(roles),
                "roles": roles,
                "scopes": [_tenant_admin_scope_payload(member, scope) for scope in member.scopes],
            }
        )
    return TenantAdminUserPage(items=tuple(items), total=result.total)


async def create_admin_user_with_tenant_member(
    *,
    tenant_id: str,
    username: str,
    password: str,
    display_name: str,
    status: str,
    session_user: AdminSessionUser,
    user_repository: AdminUserRepository,
    member_repository: AdminTenantMemberRepository,
    identity_security: IdentitySecurity,
    phone: str | None = None,
    email: str | None = None,
    created_source: str = "tenant_admin",
) -> tuple[dict[str, object], dict[str, object]]:
    """Atomically create an admin identity and its initial tenant membership."""

    user = await build_new_admin_user(
        username=username,
        password=password,
        display_name=display_name,
        status=status,
        phone=phone,
        email=email,
        created_tenant_id=tenant_id,
        created_source=created_source,
        actor_admin_user_id=session_user.user.id,
        user_repository=user_repository,
        identity_security=identity_security,
    )
    user = user.model_copy(update={"id": new_entity_id()})
    saved_user, saved_member = await member_repository.create_identity_and_member(
        user,
        AdminTenantMember(
            admin_user_id=user.id,
            tenant_id=tenant_id,
            status=status,
            scope_mode=AdminScopeType.TENANT.value,
            created_by_admin_user_id=session_user.user.id,
            updated_by_admin_user_id=session_user.user.id,
        ),
    )
    return (
        saved_user.model_dump(mode="json", exclude={"password_hash"}),
        tenant_member_payload(saved_member),
    )


async def build_new_admin_user(
    *,
    username: str,
    password: str,
    display_name: str,
    status: str,
    phone: str | None,
    email: str | None,
    created_tenant_id: str | None,
    created_source: str,
    actor_admin_user_id: str | None,
    user_repository: AdminUserRepository,
    identity_security: IdentitySecurity,
) -> AdminUser:
    """Validate and build one unsaved non-super administrator identity."""

    username = username.strip()
    if not username:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "Username cannot be empty.")
    normalized_username = canonical_stable_code(username)
    if len(username) > 64:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Username cannot exceed 64 characters.",
        )
    phone = normalize_phone(phone)
    email = normalize_email(email)
    if await user_repository.get_by_username(username) is not None:
        raise ApplicationError(ApplicationErrorKind.CONFLICT, "Username already exists.")
    await ensure_unique_contact(
        user_repository,
        phone=phone,
        email=email,
        current_user_id=None,
    )
    return AdminUser(
        username=username,
        normalized_username=normalized_username,
        password_hash=await identity_security.hash_password_async(password),
        display_name=display_name,
        phone=phone,
        email=email,
        status=status,
        is_super=False,
        created_tenant_id=created_tenant_id,
        created_source=created_source,
        created_by_admin_user_id=actor_admin_user_id,
        updated_by_admin_user_id=actor_admin_user_id,
    )


def ensure_admin_identity_contact_matches(
    user: AdminUser,
    *,
    phone: str | None,
    email: str | None,
) -> None:
    """Validate optional contact fields against an existing identity."""

    next_phone = normalize_phone(phone)
    next_email = normalize_email(email)
    if next_phone is not None and user.phone != next_phone:
        raise ApplicationError(ApplicationErrorKind.CONFLICT, "identity_conflict")
    if next_email is not None and user.email != next_email:
        raise ApplicationError(ApplicationErrorKind.CONFLICT, "identity_conflict")


async def update_tenant_admin_user(
    user_id: str,
    *,
    display_name: str | None,
    status: str | None,
    phone: str | None,
    email: str | None,
    session_user: AdminSessionUser,
    scope: AdminScopeRef,
    user_repository: AdminUserRepository,
    member_repository: AdminTenantMemberRepository,
    actor_admin_user_id: str | None = None,
) -> dict[str, object]:
    """Update an administrator from a tenant account-management context."""

    member = await ensure_admin_member_scope(
        target_admin_user_id=user_id,
        session_user=session_user,
        scope=scope,
        member_repository=member_repository,
        permission_code="admins.update",
    )
    ensure_can_manage_admin_member(
        session_user=session_user,
        target_admin_user_id=user_id,
        target_member=member,
    )
    if any(value is not None for value in (display_name, phone, email)):
        await _require_exclusive_admin_identity_tenant(
            user_id,
            tenant_id=scope.scope_tenant_id,
            session_user=session_user,
            member_repository=member_repository,
        )
        updated = await update_admin_user_identity(
            user_id,
            display_name=display_name,
            phone=phone,
            email=email,
            actor_admin_user_id=actor_admin_user_id,
            user_repository=user_repository,
        )
    else:
        current_user = await user_repository.get_by_id(user_id)
        if current_user is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Admin user does not exist.")
        updated = current_user.model_dump(mode="json", exclude={"password_hash"})
    if status is not None and status != member.status:
        member = await member_repository.save_member(
            member.model_copy(
                update={
                    "status": status,
                    "updated_by_admin_user_id": actor_admin_user_id,
                }
            )
        )
    return {
        **updated,
        "tenant_member_id": member.id,
        "tenant_id": member.tenant_id,
        "tenant_admin_status": member.status,
        "scope_mode": str(member.scope_mode),
        "roles": _tenant_admin_roles(member),
        "scopes": [_tenant_admin_scope_payload(member, item) for item in member.scopes],
    }


async def update_admin_user_identity(
    user_id: str,
    *,
    display_name: str | None,
    phone: str | None,
    email: str | None,
    actor_admin_user_id: str | None,
    user_repository: AdminUserRepository,
) -> dict[str, object]:
    """Update mutable fields of one non-super administrator identity."""

    user = await user_repository.get_by_id(user_id)
    if user is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Admin user does not exist.")
    if user.is_super:
        raise ApplicationError(
            ApplicationErrorKind.BAD_REQUEST,
            "Super admin accounts cannot be updated here.",
        )
    next_phone = normalize_phone(phone) if phone is not None else user.phone
    next_email = normalize_email(email) if email is not None else user.email
    await ensure_unique_contact(
        user_repository,
        phone=next_phone,
        email=next_email,
        current_user_id=user.id,
    )
    saved = await user_repository.save(
        user.model_copy(
            update={
                "display_name": display_name if display_name is not None else user.display_name,
                "phone": next_phone,
                "email": next_email,
                "updated_by_admin_user_id": actor_admin_user_id,
            }
        )
    )
    return saved.model_dump(mode="json", exclude={"password_hash"})


async def ensure_admin_password_reset_scope(
    *,
    target_admin_user_id: str,
    session_user: AdminSessionUser,
    scope: AdminScopeRef,
    member_repository: AdminTenantMemberRepository,
) -> None:
    """Validate that the target administrator is a member under the reset scope."""

    member = await ensure_admin_member_scope(
        target_admin_user_id=target_admin_user_id,
        session_user=session_user,
        scope=scope,
        member_repository=member_repository,
        permission_code="admins.reset_password",
    )
    ensure_can_manage_admin_member(
        session_user=session_user,
        target_admin_user_id=target_admin_user_id,
        target_member=member,
    )
    await _require_exclusive_admin_identity_tenant(
        target_admin_user_id,
        tenant_id=scope.scope_tenant_id,
        session_user=session_user,
        member_repository=member_repository,
    )


async def reset_admin_user_password(
    user_id: str,
    password: str,
    user_repository: AdminUserRepository,
    *,
    identity_security: IdentitySecurity,
    actor_admin_user_id: str | None = None,
) -> None:
    """Reset one non-super administrator password and revoke existing tokens."""

    user = await user_repository.get_by_id(user_id)
    if user is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Admin user does not exist.")
    if user.is_super:
        raise ApplicationError(
            ApplicationErrorKind.BAD_REQUEST,
            "Super admin password can only be changed by itself.",
        )
    await user_repository.save(
        user.model_copy(
            update={
                "password_hash": await identity_security.hash_password_async(password),
                "token_version": user.token_version + 1,
                "updated_by_admin_user_id": actor_admin_user_id,
            }
        )
    )


async def ensure_admin_member_scope(
    *,
    target_admin_user_id: str,
    session_user: AdminSessionUser,
    scope: AdminScopeRef,
    member_repository: AdminTenantMemberRepository,
    permission_code: str,
) -> AdminTenantMember:
    """Require a target membership covered by the requested operation scope."""

    _require_scoped_permission(session_user, permission_code, scope)
    member = await member_repository.get_by_admin_and_tenant(
        target_admin_user_id,
        scope.scope_tenant_id,
    )
    if member is not None and _member_account_scope_matches(member, scope):
        return member
    raise ApplicationError(
        ApplicationErrorKind.FORBIDDEN,
        "Target admin is not assigned inside this scope.",
    )


async def ensure_unique_contact(
    user_repository: AdminUserRepository,
    *,
    phone: str | None,
    email: str | None,
    current_user_id: str | None,
) -> None:
    if phone is not None:
        existing_phone = await user_repository.get_by_phone(phone)
        if existing_phone is not None and existing_phone.id != current_user_id:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "identity_conflict")
    if email is not None:
        existing_email = await user_repository.get_by_email(email)
        if existing_email is not None and existing_email.id != current_user_id:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "identity_conflict")


async def _require_exclusive_admin_identity_tenant(
    admin_user_id: str,
    *,
    tenant_id: str,
    session_user: AdminSessionUser,
    member_repository: AdminTenantMemberRepository,
) -> None:
    if session_user.is_super:
        return
    if await member_repository.has_membership_outside_tenant(admin_user_id, tenant_id):
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            "跨租户共享的管理员身份只能由超级管理员或账号本人修改。",
        )


def normalize_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    return phone.strip() or None


def normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    return email.strip().lower() or None


def _member_account_scope_matches(member: AdminTenantMember, scope: AdminScopeRef) -> bool:
    if member.granted_scopes:
        return any(scope_contains(scope, target_scope) for target_scope in member.granted_scopes)
    return scope.scope_type is AdminScopeType.TENANT and scope.scope_tenant_id == member.tenant_id


def _tenant_admin_roles(member: AdminTenantMember) -> list[dict[str, object]]:
    roles: dict[str, dict[str, object]] = {}
    for tenant_role in member.active_roles:
        role_id = tenant_role.role.id if tenant_role.role else tenant_role.role_id
        if role_id in roles:
            continue
        roles[role_id] = {
            "id": role_id,
            "role_code": tenant_role.role.role_code if tenant_role.role else "",
            "role_name": (tenant_role.role.role_name if tenant_role.role else f"role_id={role_id}"),
        }
    return list(roles.values())


def _tenant_admin_scope_payload(
    member: AdminTenantMember,
    member_scope: AdminTenantScope,
) -> dict[str, object]:
    scope = member_scope.scope
    return {
        "tenant_member_id": member.id,
        "scope_id": member_scope.id,
        "scope_type": scope.scope_type.value,
        "scope_tenant_id": scope.scope_tenant_id,
        "scope_organization_unit_id": scope.scope_organization_unit_id,
        "status": member.status,
    }


def _require_scoped_permission(
    session_user: AdminSessionUser,
    permission_code: str,
    scope: AdminScopeRef,
) -> None:
    if session_user.is_super:
        return
    if permission_code not in session_user.permission_codes_for_scope(scope):
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            f"Missing scoped permission: {permission_code}",
        )


def _admin_audit_actor(session_user: AdminSessionUser) -> AdminAuditActor:
    return AdminAuditActor(
        admin_user_id=session_user.user.id,
        is_super=session_user.is_super,
    )


def _admin_user_audit_summary(payload: dict[str, object] | None) -> dict[str, object]:
    if payload is None:
        return {}
    return {
        key: payload.get(key)
        for key in (
            "id",
            "username",
            "display_name",
            "phone",
            "email",
            "status",
            "is_super",
            "created_tenant_id",
            "created_source",
        )
        if key in payload
    }
