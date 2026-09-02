"""致知-specific identity, authentication, and authorization package."""

from zhizhi_platform.iam.admin_runtime import ZhizhiAdminIamRuntime
from zhizhi_platform.iam.admin_seed import (
    ADMIN_PERMISSION_SEEDS,
    AdminSeedError,
    InstallationState,
    InstallationStatus,
    SuperAdminBootstrapInput,
    get_installation_status,
    initialize_installation,
    seed_admin_security,
)
from zhizhi_platform.iam.admin_user_service import (
    AdminUserAdminService,
    CreateOrBindAdminUserCommand,
    ResetAdminPasswordCommand,
    UpdateAdminUserCommand,
)
from zhizhi_platform.iam.authorization import (
    ensure_admin_permission,
    ensure_admin_scoped_permission,
    ensure_any_admin_permission,
    ensure_super_admin,
    has_admin_parent_scoped_permission,
    has_admin_permission,
    has_admin_scoped_permission,
    permission_view_scopes,
)
from zhizhi_platform.iam.errors import (
    AuthorizationCatalogCapacityExceededError,
    OrganizationDirectoryCapacityExceededError,
)
from zhizhi_platform.iam.identity import AccessScope, OrganizationUnitRef, ScopeType
from zhizhi_platform.iam.models import (
    AdminNavigationItem,
    AdminPermission,
    AdminRole,
    AdminRolePage,
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
    AdminTenantMember,
    AdminTenantRole,
    AdminTenantScope,
    AdminUser,
    ScopeCatalogNode,
    scope_contains,
    scope_strictly_contains,
)
from zhizhi_platform.iam.organization_service import (
    CreateOrganizationUnitCommand,
    CreateTenantCommand,
    OrganizationAdminService,
    UpdateOrganizationUnitCommand,
    UpdateTenantCommand,
)
from zhizhi_platform.iam.passwords import hash_password, verify_password
from zhizhi_platform.iam.ports import OrganizationDirectory, OrganizationDirectoryEntry
from zhizhi_platform.iam.role_service import (
    CreateRoleCommand,
    RoleAdminService,
    UpdateRoleCommand,
)
from zhizhi_platform.iam.security import DefaultIdentitySecurity
from zhizhi_platform.iam.services import (
    ADMIN_NAVIGATION_ITEMS,
    AdminAuthService,
    AdminLoginBlockedError,
)
from zhizhi_platform.iam.settings import (
    IamLimitsSettings,
    JwtSettings,
    LoginThrottleSettings,
    require_jwt_signing_key,
    validate_security_configuration,
)
from zhizhi_platform.iam.tenant_member_service import (
    ReplaceTenantMemberAuthorizationCommand,
    TenantMemberAdminService,
)
from zhizhi_platform.iam.throttle import (
    LoginThrottle,
    LoginThrottleDecision,
    MemoryLoginThrottleBackend,
    RedisLoginThrottleBackend,
    validate_login_throttle_configuration,
)

__all__ = [
    "ADMIN_NAVIGATION_ITEMS",
    "ADMIN_PERMISSION_SEEDS",
    "AccessScope",
    "AdminAuthService",
    "AdminLoginBlockedError",
    "AdminNavigationItem",
    "AdminPermission",
    "AdminRole",
    "AdminRolePage",
    "AdminSeedError",
    "AdminScopeRef",
    "AdminScopeType",
    "AdminSessionUser",
    "AdminTenantMember",
    "AdminTenantRole",
    "AdminTenantScope",
    "AdminUser",
    "AdminUserAdminService",
    "OrganizationDirectory",
    "OrganizationDirectoryCapacityExceededError",
    "OrganizationDirectoryEntry",
    "AuthorizationCatalogCapacityExceededError",
    "CreateRoleCommand",
    "CreateOrganizationUnitCommand",
    "CreateTenantCommand",
    "CreateOrBindAdminUserCommand",
    "DefaultIdentitySecurity",
    "ZhizhiAdminIamRuntime",
    "ensure_admin_permission",
    "ensure_admin_scoped_permission",
    "ensure_any_admin_permission",
    "ensure_super_admin",
    "IamLimitsSettings",
    "InstallationState",
    "InstallationStatus",
    "JwtSettings",
    "LoginThrottle",
    "LoginThrottleDecision",
    "LoginThrottleSettings",
    "MemoryLoginThrottleBackend",
    "OrganizationAdminService",
    "OrganizationUnitRef",
    "RedisLoginThrottleBackend",
    "ResetAdminPasswordCommand",
    "ReplaceTenantMemberAuthorizationCommand",
    "RoleAdminService",
    "ScopeType",
    "ScopeCatalogNode",
    "SuperAdminBootstrapInput",
    "TenantMemberAdminService",
    "UpdateRoleCommand",
    "UpdateOrganizationUnitCommand",
    "UpdateTenantCommand",
    "UpdateAdminUserCommand",
    "hash_password",
    "has_admin_permission",
    "has_admin_parent_scoped_permission",
    "has_admin_scoped_permission",
    "get_installation_status",
    "initialize_installation",
    "permission_view_scopes",
    "require_jwt_signing_key",
    "scope_contains",
    "scope_strictly_contains",
    "seed_admin_security",
    "validate_login_throttle_configuration",
    "validate_security_configuration",
    "verify_password",
]
