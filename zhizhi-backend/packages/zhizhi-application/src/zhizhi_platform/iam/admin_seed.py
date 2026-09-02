"""致知 administrator permission and one-time root-account seed operations."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gewu_core.blocking import run_cpu_task
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminPermissionModel,
    AdminRolePermissionModel,
    AdminUserModel,
)
from zhizhi_platform.iam.codes import canonical_stable_code
from zhizhi_platform.iam.passwords import hash_password

ADMIN_PERMISSION_SEEDS: tuple[tuple[str, str, str], ...] = (
    ("org.view", "Organization view", "org"),
    ("org.manage", "Organization management", "org"),
    ("admins.view", "Admin account view", "admins"),
    ("admins.create", "Admin account create", "admins"),
    ("admins.update", "Admin account update", "admins"),
    ("admins.assign_role", "Admin scoped role assignment", "admins"),
    ("admins.reset_password", "Admin password reset", "admins"),
    ("llm.view", "LLM config view", "llm"),
    ("llm.bindings.edit", "LLM binding edit", "llm"),
    ("scene_git.view", "Scene Git entitlement view", "scene_git"),
    ("scene_git.entitlements.edit", "Scene Git entitlement edit", "scene_git"),
    ("data_source.view", "Data source view", "data_source"),
    ("data_source.bindings.edit", "Data source allocation edit", "data_source"),
    ("skills.view", "Skill view", "skills"),
    ("skills.edit", "Skill edit", "skills"),
    ("scenes.view", "Scene view", "scenes"),
    ("scenes.edit", "Scene edit", "scenes"),
)

REMOVED_ADMIN_PERMISSION_CODES = frozenset(
    {
        "account.view",
        "accounts.view",
        "admin_account.view",
        "admin_content.edit",
        "admin_content.view",
        "content.edit",
        "content.view",
        "end_users.create",
        "end_users.reset_password",
        "end_users.update",
        "end_users.view",
        "admin_grant.assign",
        "admin_grant.revoke",
        "admin_grant.view",
        "admin_role.assign_permission",
        "admin_role.create",
        "admin_role.update",
        "admin_role.view",
        "admin_scope.view",
        "admin_skill.edit",
        "admin_skill.view",
        "admin_user.create",
        "admin_user.reset_password",
        "admin_user.update",
        "admin_user.view",
        "data_source.edit",
        "dashboard.view",
        "grants.assign",
        "grants.revoke",
        "grants.scope.view",
        "grants.view",
        "llm.credentials.edit",
        "llm.edit",
        "llm.test",
        "llm.validate",
        "org.areas.edit",
        "org.tenant_organization_units.edit",
        "org.teams.edit",
        "org.tenants.edit",
        "roles.assign_permission",
        "roles.create",
        "roles.update",
        "roles.view",
        "users.create",
        "users.reset_password",
        "users.update",
        "users.view",
    }
)


class AdminSeedError(Exception):
    """Admin bootstrap error with a CLI-friendly status code."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SuperAdminBootstrapInput(BaseModel):
    """Explicit one-time super-admin bootstrap values."""

    model_config = ConfigDict(frozen=True)

    username: str
    password: str
    display_name: str = "Super Admin"


async def seed_admin_security(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Apply the target permission dictionary without creating an account."""

    async with session_factory() as session:
        try:
            await _seed_admin_security_once(session)
        except IntegrityError:
            await session.rollback()
            await _seed_admin_security_once(session)


async def _seed_admin_security_once(session: AsyncSession) -> None:
    permission_rows = {
        row.permission_code: row for row in await session.scalars(select(AdminPermissionModel))
    }
    await _delete_removed_permissions(session, permission_rows)
    for permission_code, permission_name, module in ADMIN_PERMISSION_SEEDS:
        row = permission_rows.get(permission_code)
        if row is None:
            session.add(
                AdminPermissionModel(
                    permission_code=permission_code,
                    permission_name=permission_name,
                    module=module,
                    description=permission_name,
                    status="active",
                )
            )
            continue
        row.permission_name = permission_name
        row.module = module
        row.description = permission_name
        row.status = "active"
    await session.commit()


async def super_admin_exists(
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """Return whether the database already contains a super-admin account."""

    async with session_factory() as session:
        return await _get_super_admin(session) is not None


async def initialize_super_admin(
    session_factory: async_sessionmaker[AsyncSession],
    bootstrap_input: SuperAdminBootstrapInput,
) -> AdminUserModel:
    """Create the only super-admin account from explicit command input."""

    username = _required_super_admin_username(bootstrap_input.username)
    password = _required_value(
        bootstrap_input.password,
        "Super admin password cannot be empty.",
    )
    display_name = _required_value(
        bootstrap_input.display_name,
        "Super admin display name cannot be empty.",
    )
    password_hash = await run_cpu_task(hash_password, password)
    async with session_factory() as session:
        if await _get_super_admin(session) is not None:
            raise AdminSeedError(409, "Super admin already exists.")
        if await _get_user_by_username(session, username) is not None:
            raise AdminSeedError(409, "Username already exists.")
        user = AdminUserModel(
            username=username,
            normalized_username=canonical_stable_code(username),
            password_hash=password_hash,
            display_name=display_name,
            status="active",
            is_super=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


def _required_value(value: str, message: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise AdminSeedError(400, message)
    return normalized


def _required_super_admin_username(value: str) -> str:
    username = _required_value(value, "Super admin username cannot be empty.")
    if len(username) > 64:
        raise AdminSeedError(400, "Super admin username cannot exceed 64 characters.")
    if len(canonical_stable_code(username)) > 256:
        raise AdminSeedError(
            400,
            "Normalized super admin username cannot exceed 256 characters.",
        )
    return username


async def _get_super_admin(session: AsyncSession) -> AdminUserModel | None:
    return cast(
        AdminUserModel | None,
        await session.scalar(
            select(AdminUserModel)
            .where(AdminUserModel.is_super.is_(True))
            .order_by(AdminUserModel.id.asc())
            .limit(1)
        ),
    )


async def _get_user_by_username(
    session: AsyncSession,
    username: str,
) -> AdminUserModel | None:
    return cast(
        AdminUserModel | None,
        await session.scalar(
            select(AdminUserModel).where(
                AdminUserModel.normalized_username == canonical_stable_code(username)
            )
        ),
    )


async def _delete_removed_permissions(
    session: AsyncSession,
    permission_rows: dict[str, AdminPermissionModel],
) -> None:
    for permission_code in REMOVED_ADMIN_PERMISSION_CODES:
        row = permission_rows.get(permission_code)
        if row is None:
            continue
        bindings = list(
            await session.scalars(
                select(AdminRolePermissionModel).where(
                    AdminRolePermissionModel.permission_id == row.id
                )
            )
        )
        for binding in bindings:
            await session.delete(binding)
        await session.delete(row)
        permission_rows.pop(permission_code, None)
