"""SQLAlchemy administrator identity repository."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from gewu_core.time import utc_now
from zhizhi_platform.iam.adapters.mysql.models import AdminUserModel
from zhizhi_platform.iam.codes import canonical_stable_code
from zhizhi_platform.iam.models import AdminUser

SessionFactory = Callable[[], AsyncSession]


def admin_user_to_domain(row: AdminUserModel) -> AdminUser:
    return AdminUser(
        id=row.id,
        username=row.username,
        normalized_username=row.normalized_username,
        password_hash=row.password_hash,
        display_name=row.display_name,
        phone=row.phone,
        email=row.email,
        status=row.status,
        is_super=row.is_super,
        token_version=row.token_version,
        last_login_time=row.last_login_time,
        created_tenant_id=row.created_tenant_id,
        created_source=row.created_source,
        created_by_admin_user_id=row.created_by_admin_user_id,
        updated_by_admin_user_id=row.updated_by_admin_user_id,
        created_at=row.create_time,
        updated_at=row.update_time,
    )


class MysqlAdminUserRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    async def get_by_id(self, user_id: str) -> AdminUser | None:
        async with self._sessions() as session:
            row = await session.get(AdminUserModel, user_id)
            return admin_user_to_domain(row) if row else None

    async def get_by_username(self, username: str) -> AdminUser | None:
        return await self._get_by(
            AdminUserModel.normalized_username == canonical_stable_code(username)
        )

    async def get_by_phone(self, phone: str) -> AdminUser | None:
        return await self._get_by(AdminUserModel.phone == phone)

    async def get_by_email(self, email: str) -> AdminUser | None:
        return await self._get_by(AdminUserModel.email == email)

    async def get_super_admin(self) -> AdminUser | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(AdminUserModel)
                .where(AdminUserModel.is_super.is_(True))
                .order_by(AdminUserModel.id.asc())
                .limit(1)
            )
            return admin_user_to_domain(row) if row else None

    async def list_users(self) -> Sequence[AdminUser]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(AdminUserModel)
                .where(AdminUserModel.is_super.is_(False))
                .order_by(AdminUserModel.id.asc())
            )
            return tuple(admin_user_to_domain(row) for row in rows)

    async def save(self, user: AdminUser) -> AdminUser:
        async with self._sessions() as session:
            row = await session.get(AdminUserModel, user.id) if user.id else None
            if row is None:
                row = AdminUserModel(
                    username=user.username,
                    normalized_username=canonical_stable_code(user.username),
                    password_hash=user.password_hash,
                )
                session.add(row)
            row.display_name = user.display_name
            row.phone = user.phone
            row.email = user.email
            row.status = user.status
            row.is_super = user.is_super
            row.token_version = user.token_version
            row.last_login_time = user.last_login_time
            row.created_tenant_id = user.created_tenant_id
            row.created_source = user.created_source
            row.created_by_admin_user_id = user.created_by_admin_user_id
            row.updated_by_admin_user_id = user.updated_by_admin_user_id
            row.password_hash = user.password_hash
            await session.commit()
            await session.refresh(row)
            return admin_user_to_domain(row)

    async def touch_last_login(self, user_id: str) -> None:
        async with self._sessions() as session:
            row = await session.get(AdminUserModel, user_id)
            if row is None:
                return
            row.last_login_time = utc_now()
            await session.commit()

    async def _get_by(self, condition: ColumnElement[bool]) -> AdminUser | None:
        async with self._sessions() as session:
            row = await session.scalar(select(AdminUserModel).where(condition))
            return admin_user_to_domain(row) if row else None
