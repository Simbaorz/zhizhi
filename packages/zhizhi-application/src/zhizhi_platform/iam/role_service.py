"""Zhizhi administrator role and permission management use cases."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.iam.authorization import ensure_super_admin
from zhizhi_platform.iam.catalog import (
    DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
    project_complete_catalog,
)
from zhizhi_platform.iam.models import AdminRole, AdminSessionUser
from zhizhi_platform.iam.ports import AdminRoleRepository

VALID_ROLE_STATUSES = {"active", "inactive"}


class CreateRoleCommand(BaseModel):
    """Input required to create one management role."""

    model_config = ConfigDict(frozen=True)

    role_code: str
    role_name: str
    description: str
    status: str
    is_delegable: bool


class UpdateRoleCommand(BaseModel):
    """Editable management role attributes."""

    model_config = ConfigDict(frozen=True)

    role_name: str | None
    description: str | None
    status: str | None
    is_delegable: bool | None


class RoleAdminService:
    """Handle role and permission operations for the management entrypoint."""

    def __init__(self, repository: AdminRoleRepository) -> None:
        self._repository = repository

    async def list_roles(
        self,
        session_user: AdminSessionUser,
        *,
        search: str,
        status: str,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        """Return one filtered page of roles."""

        ensure_super_admin(session_user)
        roles = await self._repository.list_roles_page(
            page=page,
            page_size=page_size,
            search=search,
            status=status,
        )
        return {
            "roles": [role.model_dump(mode="json") for role in roles.items],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": roles.total,
            },
        }

    async def create_role(
        self,
        session_user: AdminSessionUser,
        command: CreateRoleCommand,
    ) -> dict[str, object]:
        """Create one role after enforcing the global admin boundary."""

        ensure_super_admin(session_user)
        return await create_admin_role(
            role_code=command.role_code,
            role_name=command.role_name,
            description=command.description,
            status=command.status,
            is_delegable=command.is_delegable,
            repository=self._repository,
        )

    async def update_role(
        self,
        session_user: AdminSessionUser,
        role_id: str,
        command: UpdateRoleCommand,
    ) -> dict[str, object]:
        """Update one role after enforcing the global admin boundary."""

        ensure_super_admin(session_user)
        return await update_admin_role(
            role_id,
            role_name=command.role_name,
            description=command.description,
            status=command.status,
            is_delegable=command.is_delegable,
            repository=self._repository,
        )

    async def delete_role(self, session_user: AdminSessionUser, role_id: str) -> None:
        """Delete one role after enforcing the global admin boundary."""

        ensure_super_admin(session_user)
        await delete_admin_role(role_id, self._repository)

    async def list_role_permissions(
        self,
        session_user: AdminSessionUser,
        role_id: str,
    ) -> list[dict[str, object]]:
        """Return permissions assigned to one role."""

        ensure_super_admin(session_user)
        return await list_role_permissions(role_id, self._repository)

    async def replace_role_permissions(
        self,
        session_user: AdminSessionUser,
        role_id: str,
        permission_ids: list[str],
    ) -> None:
        """Replace one role's complete permission set."""

        ensure_super_admin(session_user)
        await replace_role_permissions(role_id, permission_ids, self._repository)

    async def list_permissions(
        self,
        session_user: AdminSessionUser,
    ) -> list[dict[str, object]]:
        """Return the complete permission catalog."""

        ensure_super_admin(session_user)
        return await list_admin_permissions(self._repository)


async def create_admin_role(
    *,
    role_code: str,
    role_name: str,
    description: str,
    status: str,
    is_delegable: bool,
    repository: AdminRoleRepository,
) -> dict[str, object]:
    """Create one admin role."""

    _require_role_status(status)
    if await repository.get_role_by_code(role_code) is not None:
        raise ApplicationError(ApplicationErrorKind.CONFLICT, "角色编码已存在。")
    role = await repository.save_role(
        AdminRole(
            role_code=role_code,
            role_name=role_name,
            description=description,
            status=status,
            is_delegable=is_delegable,
        )
    )
    return role.model_dump(mode="json")


async def update_admin_role(
    role_id: str,
    *,
    role_name: str | None,
    description: str | None,
    status: str | None,
    is_delegable: bool | None,
    repository: AdminRoleRepository,
) -> dict[str, object]:
    """Update one admin role."""

    role = await repository.get_role(role_id)
    if role is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "角色不存在。")
    if status is not None:
        _require_role_status(status)
    saved = await repository.save_role(
        role.model_copy(
            update={
                "role_name": role_name if role_name is not None else role.role_name,
                "description": description if description is not None else role.description,
                "status": status if status is not None else role.status,
                "is_delegable": is_delegable if is_delegable is not None else role.is_delegable,
            }
        )
    )
    return saved.model_dump(mode="json")


async def delete_admin_role(role_id: str, repository: AdminRoleRepository) -> None:
    """Delete one admin role and all of its bindings."""

    if await repository.get_role(role_id) is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "角色不存在。")
    await repository.delete_role(role_id)


async def list_role_permissions(
    role_id: str,
    repository: AdminRoleRepository,
) -> list[dict[str, object]]:
    """Return permissions assigned to one role."""

    if await repository.get_role(role_id) is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "角色不存在。")
    permissions = await repository.list_role_permissions(
        role_id,
        limit=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES + 1,
    )
    return project_complete_catalog(
        permissions,
        lambda permission: permission.model_dump(mode="json"),
        max_entries=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
        capacity_message="Role permission catalog exceeds the server limit.",
    )


async def replace_role_permissions(
    role_id: str,
    permission_ids: list[str],
    repository: AdminRoleRepository,
) -> None:
    """Replace one role's permissions."""

    if await repository.get_role(role_id) is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "角色不存在。")
    unique_permission_ids = list(dict.fromkeys(permission_ids))
    available_permission_ids = {
        permission.id
        for permission in await repository.get_permissions_by_ids(unique_permission_ids)
    }
    missing_permission_ids = sorted(set(unique_permission_ids) - available_permission_ids)
    if missing_permission_ids:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            f"权限不存在：{', '.join(missing_permission_ids)}",
        )
    await repository.replace_role_permissions(role_id, unique_permission_ids)


async def list_admin_permissions(
    repository: AdminRoleRepository,
) -> list[dict[str, object]]:
    """Return all admin permissions."""

    permissions = await repository.list_permissions(limit=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES + 1)
    return project_complete_catalog(
        permissions,
        lambda permission: permission.model_dump(mode="json"),
        max_entries=DEFAULT_COMPLETE_CATALOG_MAX_ENTRIES,
        capacity_message="Permission catalog exceeds the server limit.",
    )


def _require_role_status(status: str) -> None:
    if status not in VALID_ROLE_STATUSES:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "角色状态必须是 active 或 inactive。",
        )
