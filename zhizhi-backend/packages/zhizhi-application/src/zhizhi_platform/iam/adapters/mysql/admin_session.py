"""Complete administrator session projection."""

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.iam.models import (
    AdminPermission,
    AdminRole,
    AdminSessionUser,
    AdminTenantMember,
    AdminUser,
)
from zhizhi_platform.iam.ports import AdminTenantMemberRepository


class MysqlAdminSessionRepository:
    def __init__(
        self,
        tenant_member_repository: AdminTenantMemberRepository,
        *,
        max_tenant_memberships: int = 256,
    ) -> None:
        if max_tenant_memberships < 1:
            raise ValueError("max_tenant_memberships must be at least 1")
        self._members = tenant_member_repository
        self._max_memberships = max_tenant_memberships

    async def load_session_user(self, user: AdminUser) -> AdminSessionUser:
        members = tuple(
            await self._members.list_by_principal(
                user.id,
                active_only=True,
                limit=self._max_memberships + 1,
            )
        )
        if len(members) > self._max_memberships:
            raise ApplicationError(
                ApplicationErrorKind.UNAVAILABLE,
                "Admin session tenant memberships exceed the server limit.",
            )
        return AdminSessionUser(
            user=user,
            roles=_aggregate_roles(members),
            permissions=_aggregate_permissions(members),
            tenant_members=members,
        )


def _aggregate_roles(members: tuple[AdminTenantMember, ...]) -> tuple[AdminRole, ...]:
    roles: dict[str, AdminRole] = {}
    for member in members:
        for tenant_role in member.active_roles:
            if tenant_role.role is not None:
                roles[tenant_role.role.id] = tenant_role.role
    return tuple(roles.values())


def _aggregate_permissions(
    members: tuple[AdminTenantMember, ...],
) -> tuple[AdminPermission, ...]:
    permissions: dict[str, AdminPermission] = {}
    for member in members:
        for tenant_role in member.active_roles:
            for permission in tenant_role.permissions:
                permissions[permission.id] = permission
    return tuple(permissions.values())
