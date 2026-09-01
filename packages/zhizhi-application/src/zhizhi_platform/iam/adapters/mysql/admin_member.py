"""Read-side SQLAlchemy adapter for scoped administrator memberships."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import cast

from sqlalchemy import and_, case, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zhizhi_platform.iam.adapters.mysql.models import (
    AdminPermissionModel,
    AdminRoleModel,
    AdminRolePermissionModel,
    AdminTenantMemberModel,
    AdminTenantRoleModel,
    AdminTenantScopeModel,
    AdminUserModel,
)
from zhizhi_platform.iam.catalog import project_complete_catalog
from zhizhi_platform.iam.models import (
    AdminPermission,
    AdminRole,
    AdminScopeRef,
    AdminScopeType,
    AdminTenantAdminPage,
    AdminTenantAdminRow,
    AdminTenantMember,
    AdminTenantRole,
    AdminTenantScope,
    AdminUser,
)

SessionFactory = Callable[[], AsyncSession]


class MysqlAdminTenantMemberRepository:
    """Load complete authorization state without lazy ORM relationships."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        max_authorization_rows: int = 4096,
        max_permission_rows: int = 16384,
    ) -> None:
        if max_authorization_rows < 1 or max_permission_rows < 1:
            raise ValueError("Admin authorization row limits must be at least 1")
        self._sessions = session_factory
        self._max_authorization_rows = max_authorization_rows
        self._max_permission_rows = max_permission_rows

    async def list_by_principal(
        self,
        admin_user_id: str,
        *,
        active_only: bool = True,
        limit: int | None = None,
    ) -> Sequence[AdminTenantMember]:
        async with self._sessions() as session:
            statement = select(AdminTenantMemberModel).where(
                AdminTenantMemberModel.admin_user_id == admin_user_id
            )
            if active_only:
                statement = statement.where(AdminTenantMemberModel.status == "active")
            statement = statement.order_by(AdminTenantMemberModel.tenant_id.asc())
            if limit is not None:
                statement = statement.limit(limit)
            rows = tuple(await session.scalars(statement))
        return await self._hydrate(rows)

    async def get(self, member_id: str) -> AdminTenantMember | None:
        """Return one tenant member with its complete authorization state."""

        async with self._sessions() as session:
            row = await session.get(AdminTenantMemberModel, member_id)
        return (await self._hydrate((row,)))[0] if row is not None else None

    async def list_admins_page(
        self,
        tenant_id: str,
        *,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "all",
    ) -> AdminTenantAdminPage:
        """Return one SQL-filtered page of non-super tenant administrators."""

        active_condition = and_(
            AdminTenantMemberModel.status == "active",
            AdminUserModel.status == "active",
        )
        conditions = [
            AdminTenantMemberModel.tenant_id == tenant_id,
            AdminUserModel.is_super.is_(False),
        ]
        if status == "active":
            conditions.append(active_condition)
        elif status == "inactive":
            conditions.append(~active_condition)
        keyword = search.strip().lower()
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            role_match = (
                select(AdminTenantRoleModel.id)
                .join(AdminRoleModel, AdminRoleModel.id == AdminTenantRoleModel.role_id)
                .where(
                    AdminTenantRoleModel.tenant_member_id == AdminTenantMemberModel.id,
                    or_(
                        func.lower(AdminRoleModel.role_name).like(pattern, escape="\\"),
                        func.lower(AdminRoleModel.role_code).like(pattern, escape="\\"),
                    ),
                )
                .exists()
            )
            conditions.append(
                or_(
                    func.lower(AdminUserModel.username).like(pattern, escape="\\"),
                    func.lower(AdminUserModel.display_name).like(pattern, escape="\\"),
                    func.lower(AdminUserModel.phone).like(pattern, escape="\\"),
                    func.lower(AdminUserModel.email).like(pattern, escape="\\"),
                    role_match,
                )
            )
        async with self._sessions() as session:
            base_statement = (
                select(AdminTenantMemberModel, AdminUserModel)
                .join(
                    AdminUserModel,
                    AdminUserModel.id == AdminTenantMemberModel.admin_user_id,
                )
                .where(*conditions)
            )
            rows = tuple(
                await session.execute(
                    base_statement.order_by(
                        case((active_condition, 0), else_=1).asc(),
                        AdminUserModel.username.asc(),
                        AdminUserModel.id.asc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(AdminTenantMemberModel)
                    .join(
                        AdminUserModel,
                        AdminUserModel.id == AdminTenantMemberModel.admin_user_id,
                    )
                    .where(*conditions)
                )
                or 0
            )
        members = await self._hydrate(tuple(member for member, _user in rows))
        member_by_id = {member.id: member for member in members}
        return AdminTenantAdminPage(
            items=tuple(
                AdminTenantAdminRow(
                    user=_admin_user(user),
                    member=member_by_id[member.id],
                )
                for member, user in rows
            ),
            total=total,
        )

    async def get_by_admin_and_tenant(
        self,
        admin_user_id: str,
        tenant_id: str,
    ) -> AdminTenantMember | None:
        """Return one tenant member by its unique account and tenant pair."""

        async with self._sessions() as session:
            row = cast(
                AdminTenantMemberModel | None,
                await session.scalar(
                    select(AdminTenantMemberModel).where(
                        AdminTenantMemberModel.admin_user_id == admin_user_id,
                        AdminTenantMemberModel.tenant_id == tenant_id,
                    )
                ),
            )
        return (await self._hydrate((row,)))[0] if row is not None else None

    async def has_membership_outside_tenant(
        self,
        admin_user_id: str,
        tenant_id: str,
    ) -> bool:
        """Return whether an administrator belongs to another tenant."""

        async with self._sessions() as session:
            return bool(
                await session.scalar(
                    select(
                        exists().where(
                            AdminTenantMemberModel.admin_user_id == admin_user_id,
                            AdminTenantMemberModel.tenant_id != tenant_id,
                        )
                    )
                )
            )

    async def save_member(self, member: AdminTenantMember) -> AdminTenantMember:
        """Create or update one tenant member without changing role or scope rows."""

        async with self._sessions() as session:
            row = await self._find_existing_member(session, member)
            if row is None:
                row = AdminTenantMemberModel(
                    admin_user_id=member.admin_user_id,
                    tenant_id=member.tenant_id,
                    status=member.status,
                    scope_mode=str(member.scope_mode),
                    created_by_admin_user_id=member.created_by_admin_user_id,
                    updated_by_admin_user_id=member.updated_by_admin_user_id,
                )
                session.add(row)
            else:
                row.status = member.status
                row.scope_mode = str(member.scope_mode)
                row.updated_by_admin_user_id = member.updated_by_admin_user_id
            await session.commit()
            await session.refresh(row)
        saved = await self.get(row.id)
        if saved is None:
            raise ValueError(f"Admin tenant member {row.id} does not exist.")
        return saved

    async def create_identity_and_member(
        self,
        user: AdminUser,
        member: AdminTenantMember,
    ) -> tuple[AdminUser, AdminTenantMember]:
        """Atomically create one admin identity and its initial tenant membership."""

        async with self._sessions() as session:
            user_row = AdminUserModel(
                id=user.id,
                username=user.username,
                normalized_username=user.normalized_username,
                password_hash=user.password_hash,
                display_name=user.display_name,
                phone=user.phone,
                email=user.email,
                status=user.status,
                is_super=user.is_super,
                token_version=user.token_version,
                last_login_time=user.last_login_time,
                created_tenant_id=user.created_tenant_id,
                created_source=user.created_source,
                created_by_admin_user_id=user.created_by_admin_user_id,
                updated_by_admin_user_id=user.updated_by_admin_user_id,
            )
            session.add(user_row)
            await session.flush()
            member_row = AdminTenantMemberModel(
                admin_user_id=user_row.id,
                tenant_id=member.tenant_id,
                status=member.status,
                scope_mode=str(member.scope_mode),
                created_by_admin_user_id=member.created_by_admin_user_id,
                updated_by_admin_user_id=member.updated_by_admin_user_id,
            )
            session.add(member_row)
            await session.commit()
            await session.refresh(user_row)
            await session.refresh(member_row)
        saved_member = await self.get(member_row.id)
        if saved_member is None:
            raise ValueError(f"Admin tenant member {member_row.id} does not exist.")
        return _admin_user(user_row), saved_member

    async def replace_authorization(
        self,
        member: AdminTenantMember,
        role_ids: Sequence[str],
        scopes: Sequence[AdminTenantScope],
    ) -> AdminTenantMember:
        """Atomically replace member status, roles, and data scopes."""

        async with self._sessions() as session:
            row = await self._find_existing_member(session, member)
            if row is None:
                raise ValueError(f"Admin tenant member {member.id} does not exist.")
            row.status = member.status
            row.scope_mode = str(member.scope_mode)
            row.updated_by_admin_user_id = member.updated_by_admin_user_id
            await session.execute(
                delete(AdminTenantRoleModel).where(AdminTenantRoleModel.tenant_member_id == row.id)
            )
            await session.execute(
                delete(AdminTenantScopeModel).where(
                    AdminTenantScopeModel.tenant_member_id == row.id
                )
            )
            for role_id in dict.fromkeys(role_ids):
                session.add(AdminTenantRoleModel(tenant_member_id=row.id, role_id=role_id))
            for scope in scopes:
                session.add(
                    AdminTenantScopeModel(
                        tenant_member_id=row.id,
                        scope_type=scope.scope.scope_type.value,
                        scope_organization_unit_id=scope.scope.scope_organization_unit_id,
                    )
                )
            await session.commit()
        saved = await self.get(member.id)
        if saved is None:
            raise ValueError(f"Admin tenant member {member.id} does not exist.")
        return saved

    @staticmethod
    async def _find_existing_member(
        session: AsyncSession,
        member: AdminTenantMember,
    ) -> AdminTenantMemberModel | None:
        if member.id:
            return await session.get(AdminTenantMemberModel, member.id)
        return cast(
            AdminTenantMemberModel | None,
            await session.scalar(
                select(AdminTenantMemberModel).where(
                    AdminTenantMemberModel.admin_user_id == member.admin_user_id,
                    AdminTenantMemberModel.tenant_id == member.tenant_id,
                )
            ),
        )

    async def _hydrate(
        self,
        members: Sequence[AdminTenantMemberModel],
    ) -> tuple[AdminTenantMember, ...]:
        if not members:
            return ()
        member_ids = tuple(member.id for member in members)
        async with self._sessions() as session:
            role_rows = project_complete_catalog(
                tuple(
                    await session.scalars(
                        select(AdminTenantRoleModel)
                        .where(AdminTenantRoleModel.tenant_member_id.in_(member_ids))
                        .order_by(AdminTenantRoleModel.id.asc())
                        .limit(self._max_authorization_rows + 1)
                    )
                ),
                lambda row: row,
                max_entries=self._max_authorization_rows,
                capacity_message="Admin authorization role assignments exceed the server limit.",
            )
            scope_rows = project_complete_catalog(
                tuple(
                    await session.scalars(
                        select(AdminTenantScopeModel)
                        .where(AdminTenantScopeModel.tenant_member_id.in_(member_ids))
                        .order_by(
                            AdminTenantScopeModel.tenant_member_id.asc(),
                            case(
                                (AdminTenantScopeModel.scope_type == "tenant", 0),
                                (
                                    AdminTenantScopeModel.scope_type == "organization_unit",
                                    1,
                                ),
                                else_=3,
                            ),
                            AdminTenantScopeModel.scope_organization_unit_id.asc(),
                            AdminTenantScopeModel.id.asc(),
                        )
                        .limit(self._max_authorization_rows + 1)
                    )
                ),
                lambda row: row,
                max_entries=self._max_authorization_rows,
                capacity_message="Admin authorization scope assignments exceed the server limit.",
            )
            role_ids = tuple(dict.fromkeys(row.role_id for row in role_rows))
            role_models = (
                tuple(
                    await session.scalars(
                        select(AdminRoleModel).where(AdminRoleModel.id.in_(role_ids))
                    )
                )
                if role_ids
                else ()
            )
            permission_rows = (
                project_complete_catalog(
                    tuple(
                        await session.execute(
                            select(AdminRolePermissionModel.role_id, AdminPermissionModel)
                            .join(
                                AdminPermissionModel,
                                AdminPermissionModel.id == AdminRolePermissionModel.permission_id,
                            )
                            .where(AdminRolePermissionModel.role_id.in_(role_ids))
                            .order_by(
                                AdminRolePermissionModel.role_id.asc(),
                                AdminPermissionModel.permission_code.asc(),
                            )
                            .limit(self._max_permission_rows + 1)
                        )
                    ),
                    lambda row: row,
                    max_entries=self._max_permission_rows,
                    capacity_message=(
                        "Admin authorization permission assignments exceed the server limit."
                    ),
                )
                if role_ids
                else []
            )
        roles = {row.id: _role(row) for row in role_models}
        permissions_by_role: dict[str, list[AdminPermission]] = {}
        for role_id, row in permission_rows:
            permissions_by_role.setdefault(role_id, []).append(_permission(row))
        roles_by_member: dict[str, list[AdminTenantRole]] = {}
        for row in role_rows:
            roles_by_member.setdefault(row.tenant_member_id, []).append(
                AdminTenantRole(
                    id=row.id,
                    tenant_member_id=row.tenant_member_id,
                    role_id=row.role_id,
                    role=roles.get(row.role_id),
                    permissions=tuple(permissions_by_role.get(row.role_id, ())),
                    created_at=row.create_time,
                    updated_at=row.update_time,
                )
            )
        tenant_by_member = {member.id: member.tenant_id for member in members}
        scopes_by_member: dict[str, list[AdminTenantScope]] = {}
        for row in scope_rows:
            scopes_by_member.setdefault(row.tenant_member_id, []).append(
                AdminTenantScope(
                    id=row.id,
                    tenant_member_id=row.tenant_member_id,
                    scope=AdminScopeRef(
                        scope_type=AdminScopeType(row.scope_type),
                        scope_tenant_id=tenant_by_member[row.tenant_member_id],
                        scope_organization_unit_id=row.scope_organization_unit_id,
                    ),
                    created_at=row.create_time,
                    updated_at=row.update_time,
                )
            )
        return tuple(
            AdminTenantMember(
                id=row.id,
                admin_user_id=row.admin_user_id,
                tenant_id=row.tenant_id,
                status=row.status,
                scope_mode=row.scope_mode,
                roles=tuple(roles_by_member.get(row.id, ())),
                scopes=tuple(scopes_by_member.get(row.id, ())),
                created_by_admin_user_id=row.created_by_admin_user_id,
                updated_by_admin_user_id=row.updated_by_admin_user_id,
                created_at=row.create_time,
                updated_at=row.update_time,
            )
            for row in members
        )


def _role(row: AdminRoleModel) -> AdminRole:
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


def _permission(row: AdminPermissionModel) -> AdminPermission:
    return AdminPermission(
        id=row.id,
        permission_code=row.permission_code,
        permission_name=row.permission_name,
        module=row.module,
        description=row.description,
        status=row.status,
    )


def _admin_user(row: AdminUserModel) -> AdminUser:
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


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
