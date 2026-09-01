"""Lifecycle-owned IAM components used by the Zhizhi Admin API."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gewu_core.config import BootstrapSettings
from zhizhi_platform.iam.adapters.mysql.admin_member import (
    MysqlAdminTenantMemberRepository,
)
from zhizhi_platform.iam.adapters.mysql.admin_org import MysqlAdminOrgReadRepository
from zhizhi_platform.iam.adapters.mysql.admin_role import MysqlAdminRoleRepository
from zhizhi_platform.iam.adapters.mysql.admin_session import (
    MysqlAdminSessionRepository,
)
from zhizhi_platform.iam.adapters.mysql.admin_user import MysqlAdminUserRepository
from zhizhi_platform.iam.adapters.mysql.organization_directory import MysqlOrganizationDirectory
from zhizhi_platform.iam.security import DefaultIdentitySecurity
from zhizhi_platform.iam.settings import (
    IamLimitsSettings,
    JwtSettings,
    LoginThrottleSettings,
    validate_security_configuration,
)
from zhizhi_platform.iam.throttle import LoginThrottle, LoginThrottleBackend


class ZhizhiAdminIamRuntime:
    """Own the administrator IAM components required by the Admin API process."""

    def __init__(
        self,
        bootstrap: BootstrapSettings,
        *,
        sessions: async_sessionmaker[AsyncSession],
        jwt: JwtSettings,
        login_throttle: LoginThrottleSettings,
        limits: IamLimitsSettings,
        login_throttle_backend: LoginThrottleBackend,
    ) -> None:
        self.bootstrap = bootstrap
        self._sessions = sessions
        self.jwt_settings = jwt
        self.login_throttle_settings = login_throttle
        self.limit_settings = limits
        self._login_throttle_backend = login_throttle_backend
        self.identity_security: DefaultIdentitySecurity | None = None
        self.admin_user_repository: MysqlAdminUserRepository | None = None
        self.admin_role_repository: MysqlAdminRoleRepository | None = None
        self.admin_tenant_member_repository: MysqlAdminTenantMemberRepository | None = None
        self.admin_org_repository: MysqlAdminOrgReadRepository | None = None
        self.organization_directory: MysqlOrganizationDirectory | None = None
        self.admin_session_repository: MysqlAdminSessionRepository | None = None
        self.admin_login_throttle: LoginThrottle | None = None
        self._started = False

    async def startup(self) -> None:
        """Validate settings and initialize Admin IAM components once."""

        if self._started:
            return
        validate_security_configuration(self.jwt_settings, self.bootstrap.mode.value)
        if self._login_throttle_backend is None:
            raise RuntimeError("A shared Admin login throttling backend is required.")
        self.identity_security = DefaultIdentitySecurity(self.jwt_settings)
        member_repository = MysqlAdminTenantMemberRepository(
            self._sessions,
            max_authorization_rows=self.limit_settings.max_admin_authorization_rows,
            max_permission_rows=self.limit_settings.max_admin_permission_rows,
        )
        self.admin_tenant_member_repository = member_repository
        self.admin_org_repository = MysqlAdminOrgReadRepository(self._sessions)
        self.organization_directory = MysqlOrganizationDirectory(
            self._sessions,
            max_query_rows=self.limit_settings.max_organization_directory_rows,
        )
        self.admin_user_repository = MysqlAdminUserRepository(self._sessions)
        self.admin_role_repository = MysqlAdminRoleRepository(self._sessions)
        self.admin_session_repository = MysqlAdminSessionRepository(
            member_repository,
            max_tenant_memberships=self.limit_settings.max_admin_session_memberships,
        )
        self.admin_login_throttle = LoginThrottle(
            self._login_throttle_backend,
            self.login_throttle_settings,
            project_name=self.bootstrap.project_name,
            mode=self.bootstrap.mode.value,
            namespace="admin-login",
        )
        self._started = True

    async def shutdown(self) -> None:
        """Clear process-owned Admin IAM components."""

        self._started = False
        self.identity_security = None
        self.admin_user_repository = None
        self.admin_role_repository = None
        self.admin_tenant_member_repository = None
        self.admin_org_repository = None
        self.organization_directory = None
        self.admin_session_repository = None
        self.admin_login_throttle = None

    @property
    def started(self) -> bool:
        return self._started
