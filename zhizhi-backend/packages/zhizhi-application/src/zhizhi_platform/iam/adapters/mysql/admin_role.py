"""SQLAlchemy persistence for 致知 administrator roles and permissions."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zhizhi_platform.iam.adapters.mysql.models import (
    AdminPermissionModel,
    AdminRoleModel,
    AdminRolePermissionModel,
    AdminTenantRoleModel,
)
from zhizhi_platform.iam.models import AdminPermission, AdminRole, AdminRolePage

SessionFactory = Callable[[], AsyncSession]


class MysqlAdminRoleRepository:
    """MySQL-backed role and permission repository."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def list_roles_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> AdminRolePage:
        """Return one filtered page and aggregate permission counts in SQL."""

        conditions = []
        if status != "all":
            conditions.append(AdminRoleModel.status == status)
        keyword = search.strip()
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            conditions.append(
                or_(
                    AdminRoleModel.role_code.ilike(pattern, escape="\\"),
                    AdminRoleModel.role_name.ilike(pattern, escape="\\"),
                    AdminRoleModel.description.ilike(pattern, escape="\\"),
                )
            )
        permission_count = (
            select(func.count())
            .select_from(AdminRolePermissionModel)
            .where(AdminRolePermissionModel.role_id == AdminRoleModel.id)
            .correlate(AdminRoleModel)
            .scalar_subquery()
        )
        async with self._session_factory() as session:
            total = int(
                await session.scalar(
                    select(func.count()).select_from(AdminRoleModel).where(*conditions)
                )
                or 0
            )
            result = await session.execute(
                select(AdminRoleModel, permission_count)
                .where(*conditions)
                .order_by(AdminRoleModel.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            roles = tuple(
                _role_to_domain(row).model_copy(update={"permission_count": int(count or 0)})
                for row, count in result.all()
            )
        return AdminRolePage(items=roles, total=total)

    async def list_active_roles(
        self,
        *,
        limit: int,
        delegable_only: bool,
    ) -> Sequence[AdminRole]:
        """Return a bounded active role catalog with permission counts."""

        if limit < 1:
            raise ValueError("limit must be greater than zero")
        conditions = [AdminRoleModel.status == "active"]
        if delegable_only:
            conditions.append(AdminRoleModel.is_delegable.is_(True))
        permission_count = (
            select(func.count())
            .select_from(AdminRolePermissionModel)
            .where(AdminRolePermissionModel.role_id == AdminRoleModel.id)
            .correlate(AdminRoleModel)
            .scalar_subquery()
        )
        async with self._session_factory() as session:
            result = await session.execute(
                select(AdminRoleModel, permission_count)
                .where(*conditions)
                .order_by(AdminRoleModel.id.asc())
                .limit(limit)
            )
            return tuple(
                _role_to_domain(row).model_copy(update={"permission_count": int(count or 0)})
                for row, count in result.all()
            )

    async def get_role(self, role_id: str) -> AdminRole | None:
        async with self._session_factory() as session:
            row = await session.get(AdminRoleModel, role_id)
            return _role_to_domain(row) if row else None

    async def get_role_by_code(self, role_code: str) -> AdminRole | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(AdminRoleModel).where(AdminRoleModel.role_code == role_code)
            )
            return _role_to_domain(row) if row else None

    async def save_role(self, role: AdminRole) -> AdminRole:
        async with self._session_factory() as session:
            row = await session.get(AdminRoleModel, role.id) if role.id else None
            if row is None:
                row = AdminRoleModel(
                    role_code=role.role_code,
                    role_name=role.role_name,
                    description=role.description,
                    status=role.status,
                    is_delegable=role.is_delegable,
                )
                session.add(row)
            else:
                row.role_code = role.role_code
                row.role_name = role.role_name
                row.description = role.description
                row.status = role.status
                row.is_delegable = role.is_delegable
            await session.commit()
            await session.refresh(row)
            return _role_to_domain(row)

    async def delete_role(self, role_id: str) -> None:
        """Delete one role and all permission and tenant-member bindings atomically."""

        async with self._session_factory() as session:
            await session.execute(
                delete(AdminRolePermissionModel).where(AdminRolePermissionModel.role_id == role_id)
            )
            await session.execute(
                delete(AdminTenantRoleModel).where(AdminTenantRoleModel.role_id == role_id)
            )
            await session.execute(delete(AdminRoleModel).where(AdminRoleModel.id == role_id))
            await session.commit()

    async def list_permissions(
        self,
        *,
        limit: int | None = None,
    ) -> Sequence[AdminPermission]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be greater than zero")
        statement = select(AdminPermissionModel).order_by(
            AdminPermissionModel.module.asc(),
            AdminPermissionModel.permission_code.asc(),
        )
        if limit is not None:
            statement = statement.limit(limit)
        async with self._session_factory() as session:
            rows = tuple(await session.scalars(statement))
            return tuple(_permission_to_domain(row) for row in rows)

    async def get_permissions_by_ids(
        self,
        permission_ids: Sequence[str],
    ) -> Sequence[AdminPermission]:
        ids = tuple(dict.fromkeys(permission_ids))
        if not ids:
            return ()
        async with self._session_factory() as session:
            rows = tuple(
                await session.scalars(
                    select(AdminPermissionModel)
                    .where(AdminPermissionModel.id.in_(ids))
                    .order_by(AdminPermissionModel.id.asc())
                )
            )
            return tuple(_permission_to_domain(row) for row in rows)

    async def list_role_permissions(
        self,
        role_id: str,
        *,
        limit: int | None = None,
    ) -> Sequence[AdminPermission]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be greater than zero")
        statement = (
            select(AdminPermissionModel)
            .join(
                AdminRolePermissionModel,
                AdminRolePermissionModel.permission_id == AdminPermissionModel.id,
            )
            .where(AdminRolePermissionModel.role_id == role_id)
            .order_by(AdminPermissionModel.permission_code.asc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        async with self._session_factory() as session:
            rows = tuple(await session.scalars(statement))
            return tuple(_permission_to_domain(row) for row in rows)

    async def role_has_active_permission_outside(
        self,
        role_id: str,
        permission_codes: Sequence[str],
    ) -> bool:
        conditions = [
            AdminRolePermissionModel.role_id == role_id,
            AdminRolePermissionModel.permission_id == AdminPermissionModel.id,
            AdminPermissionModel.status == "active",
        ]
        allowed_codes = tuple(dict.fromkeys(permission_codes))
        if allowed_codes:
            conditions.append(AdminPermissionModel.permission_code.not_in(allowed_codes))
        async with self._session_factory() as session:
            return bool(await session.scalar(select(exists().where(*conditions))))

    async def replace_role_permissions(
        self,
        role_id: str,
        permission_ids: Sequence[str],
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(AdminRolePermissionModel).where(AdminRolePermissionModel.role_id == role_id)
            )
            for permission_id in dict.fromkeys(permission_ids):
                session.add(
                    AdminRolePermissionModel(
                        role_id=role_id,
                        permission_id=permission_id,
                    )
                )
            await session.commit()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _role_to_domain(row: AdminRoleModel) -> AdminRole:
    return AdminRole(
        id=row.id,
        role_code=row.role_code,
        role_name=row.role_name,
        description=row.description,
        status=row.status,
        is_delegable=row.is_delegable,
        created_at=row.create_time,
        updated_at=row.update_time,
    )


def _permission_to_domain(row: AdminPermissionModel) -> AdminPermission:
    return AdminPermission(
        id=row.id,
        permission_code=row.permission_code,
        permission_name=row.permission_name,
        module=row.module,
        description=row.description,
        status=row.status,
    )
