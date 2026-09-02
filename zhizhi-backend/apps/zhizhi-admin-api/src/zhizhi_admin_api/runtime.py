"""Independent Admin API process composition root."""

from __future__ import annotations

from zhizhi.assets import (
    MysqlSharedAssetRepository,
    MysqlSharedSceneAssetRepository,
)

from gewu_core.apollo_config import load_settings_once
from gewu_core.config import (
    ApolloBootstrapSettings,
    BootstrapSettings,
    load_settings,
)
from gewu_core.database import DatabaseRuntime
from gewu_core.http import HttpInfrastructureRuntime, RsaPasswordTransport
from gewu_core.observability import (
    FilesystemScanRecorder,
    configure_filesystem_scan_recorder,
)
from gewu_core.redis import RedisClient
from gewu_core.runtime_health import RuntimeReadinessSnapshot
from zhizhi_admin_api.bootstrap_service import AdminBootstrapService
from zhizhi_admin_api.organization_references import MysqlOrganizationReferenceQuery
from zhizhi_admin_api.scene_git_dispatcher import CelerySceneGitSyncDispatcher
from zhizhi_admin_api.settings import AdminApiSettings
from zhizhi_admin_api.shared_asset_admin import ZhizhiAssetAdminService
from zhizhi_platform.audit import AdminAuditWriter, MysqlAdminAuditLogRepository
from zhizhi_platform.bootstrap import (
    resolve_instance_namespace,
    should_auto_create_schema,
    should_enforce_strong_secrets,
)
from zhizhi_platform.data_source import (
    ConfiguredDataSourceCredentialCipher,
    ZhizhiDataSourceAdminService,
)
from zhizhi_platform.data_source.adapters.mysql import (
    MysqlDataSourceAdminRepository,
)
from zhizhi_platform.git import (
    ConfiguredGitCredentialCipher,
    RestrictedGitRepositoryClient,
    ZhizhiGitAdminService,
)
from zhizhi_platform.git.adapters.mysql import MysqlAdminGitRepository
from zhizhi_platform.iam import (
    AdminAuthService,
    AdminUserAdminService,
    OrganizationAdminService,
    RedisLoginThrottleBackend,
    RoleAdminService,
    TenantMemberAdminService,
    ZhizhiAdminIamRuntime,
    seed_admin_security,
    validate_login_throttle_configuration,
    validate_security_configuration,
)
from zhizhi_platform.iam.adapters.mysql import MysqlAdminOrgManageRepository
from zhizhi_platform.llm import (
    ConfiguredLLMCredentialCipher,
    ProviderConnectivityTester,
    ZhizhiLLMAdminService,
)
from zhizhi_platform.llm.adapters.mysql import MysqlLLMAdminRepository
from zhizhi_platform.scene import SceneGitAdminService
from zhizhi_platform.schema import ensure_schema
from zhizhi_platform.workspace import (
    FilesystemManagedWorkspaceRepository,
    MysqlBackgroundJobRepository,
    MysqlWorkspaceSceneGitRepository,
    SceneGitSyncDispatcher,
    resolve_workspace_storage_root,
)
from zhizhi_platform.workspace.observability import (
    install_zhizhi_filesystem_metrics,
)


class ZhizhiAdminApiRuntime:
    """Own Admin HTTP, IAM persistence, and management authentication."""

    def __init__(
        self,
        bootstrap: BootstrapSettings,
        *,
        settings: AdminApiSettings | None = None,
        scene_git_dispatcher: SceneGitSyncDispatcher | None = None,
    ) -> None:
        self.bootstrap = bootstrap
        self.settings = settings
        self._http: HttpInfrastructureRuntime | None = None
        self._database: DatabaseRuntime | None = None
        self._iam: ZhizhiAdminIamRuntime | None = None
        self._redis: RedisClient | None = None
        self._scene_git_dispatcher_override = scene_git_dispatcher
        self._owned_scene_git_dispatcher: CelerySceneGitSyncDispatcher | None = None
        self.auth_service: AdminAuthService | None = None
        self.bootstrap_service: AdminBootstrapService | None = None
        self.admin_user_service: AdminUserAdminService | None = None
        self.role_service: RoleAdminService | None = None
        self.organization_service: OrganizationAdminService | None = None
        self.tenant_member_service: TenantMemberAdminService | None = None
        self.git_service: ZhizhiGitAdminService | None = None
        self.llm_service: ZhizhiLLMAdminService | None = None
        self.data_source_service: ZhizhiDataSourceAdminService | None = None
        self.skill_service: ZhizhiAssetAdminService | None = None
        self.scene_service: ZhizhiAssetAdminService | None = None
        self.audit_writer: AdminAuditWriter | None = None
        self._previous_filesystem_scan_recorder: FilesystemScanRecorder | None = None
        self._started = False

    @property
    def password_transport(self) -> RsaPasswordTransport | None:
        return self._http.password_transport if self._http is not None else None

    async def startup(self) -> None:
        if self._started:
            return
        settings = self.settings
        if settings is None:
            if isinstance(self.bootstrap, ApolloBootstrapSettings):
                settings = await load_settings_once(
                    AdminApiSettings,
                    self.bootstrap,
                    required_paths=("redis.connection",),
                )
            else:
                settings = load_settings(
                    AdminApiSettings,
                    self.bootstrap,
                    required_paths=("redis.connection",),
                )
        self.settings = settings
        try:
            await self._startup_components(settings)
        except BaseException:
            await self.shutdown()
            raise

    async def _startup_components(self, settings: AdminApiSettings) -> None:
        """Build process resources after settings have been resolved."""

        self._http = HttpInfrastructureRuntime(
            self.bootstrap,
            settings=settings,
            password_transport_settings=settings.password_transport,
            require_password_transport=bool(
                getattr(self.bootstrap, "admin_require_password_transport", False)
            ),
        )
        self._database = DatabaseRuntime(settings.db, self.bootstrap.project_home)
        self._redis = RedisClient(settings.redis)
        await self._redis.initialize()
        login_backend = RedisLoginThrottleBackend(self._redis)
        await self._http.startup()
        validate_security_configuration(
            settings.jwt,
            enforce_strong_secrets=should_enforce_strong_secrets(self.bootstrap),
            storage_encryption=settings.storage_encryption,
        )
        validate_login_throttle_configuration(
            settings.login_throttle,
            redis_enabled=settings.redis.enabled,
        )
        await self._database.startup()
        engine = self._database.engine
        sessions = self._database.sessions
        if engine is None or sessions is None:
            raise RuntimeError("Admin API database dependencies were not initialized.")
        self._iam = ZhizhiAdminIamRuntime(
            self.bootstrap,
            sessions=sessions,
            jwt=settings.jwt,
            login_throttle=settings.login_throttle,
            limits=settings.iam,
            login_throttle_backend=login_backend,
        )
        await self._iam.startup()
        await ensure_schema(
            engine,
            auto_create=should_auto_create_schema(self.bootstrap),
        )
        if (
            self._iam.admin_user_repository is None
            or self._iam.admin_session_repository is None
            or self._iam.admin_role_repository is None
            or self._iam.admin_tenant_member_repository is None
            or self._iam.admin_org_repository is None
            or self._iam.organization_directory is None
            or self._iam.identity_security is None
            or self._iam.admin_login_throttle is None
            or self.password_transport is None
        ):
            raise RuntimeError("Admin API authentication dependencies were not initialized.")
        await seed_admin_security(sessions)
        self.bootstrap_service = AdminBootstrapService(
            sessions,
            self.password_transport,
            str(getattr(self.bootstrap, "admin_bootstrap_token", "")),
        )
        self.audit_writer = AdminAuditWriter(MysqlAdminAuditLogRepository(sessions))
        self.auth_service = AdminAuthService(
            user_repository=self._iam.admin_user_repository,
            session_repository=self._iam.admin_session_repository,
            identity_security=self._iam.identity_security,
            login_throttle=self._iam.admin_login_throttle,
            password_transport=self.password_transport,
        )
        self.role_service = RoleAdminService(self._iam.admin_role_repository)
        self.organization_service = OrganizationAdminService(
            read_repository=self._iam.admin_org_repository,
            repository=MysqlAdminOrgManageRepository(
                sessions,
                MysqlOrganizationReferenceQuery(sessions),
            ),
        )
        self.admin_user_service = AdminUserAdminService(
            user_repository=self._iam.admin_user_repository,
            member_repository=self._iam.admin_tenant_member_repository,
            org_repository=self._iam.admin_org_repository,
            audit_writer=self.audit_writer,
            identity_security=self._iam.identity_security,
            password_transport=self.password_transport,
        )
        self.tenant_member_service = TenantMemberAdminService(
            member_repository=self._iam.admin_tenant_member_repository,
            user_repository=self._iam.admin_user_repository,
            role_repository=self._iam.admin_role_repository,
            org_repository=self._iam.admin_org_repository,
            audit_writer=self.audit_writer,
        )
        git_repository = MysqlAdminGitRepository(sessions)
        self.git_service = ZhizhiGitAdminService(
            repository=git_repository,
            client=RestrictedGitRepositoryClient(settings.scene_git.command_timeout_seconds),
            org_repository=self._iam.admin_org_repository,
            cipher=ConfiguredGitCredentialCipher(settings.storage_encryption.key),
        )
        self.llm_service = ZhizhiLLMAdminService(
            repository=MysqlLLMAdminRepository(
                sessions,
                self._iam.organization_directory,
            ),
            org_repository=self._iam.admin_org_repository,
            connectivity_tester=ProviderConnectivityTester(
                connect_timeout_seconds=settings.outbound_http.connect_timeout_seconds,
                pool_timeout_seconds=settings.outbound_http.pool_timeout_seconds,
            ),
            cipher=ConfiguredLLMCredentialCipher(settings.storage_encryption.key),
        )
        self.data_source_service = ZhizhiDataSourceAdminService(
            repository=MysqlDataSourceAdminRepository(
                sessions,
                self._iam.organization_directory,
            ),
            org_repository=self._iam.admin_org_repository,
            cipher=ConfiguredDataSourceCredentialCipher(settings.storage_encryption.key),
        )
        if settings.workspace.storage_root.strip():
            workspace_root = resolve_workspace_storage_root(
                settings.workspace.storage_root, self.bootstrap.project_home
            )
            workspace_repository = FilesystemManagedWorkspaceRepository(
                storage_root=workspace_root,
                max_file_bytes=settings.workspace.max_file_bytes,
                max_skill_package_bytes=settings.workspace.max_skill_package_bytes,
                max_scene_package_bytes=settings.workspace.max_scene_package_bytes,
                max_listing_entries=settings.workspace.max_listing_entries,
            )
            shared_asset_repository = MysqlSharedAssetRepository(sessions)
            self.skill_service = ZhizhiAssetAdminService(
                kind="skill",
                repository=workspace_repository,
                assets=shared_asset_repository,
                org_repository=self._iam.admin_org_repository,
            )
            dispatcher = self._scene_git_dispatcher_override
            if dispatcher is None:
                self._owned_scene_git_dispatcher = CelerySceneGitSyncDispatcher(
                    redis=settings.redis,
                    project_name=self.bootstrap.project_name,
                    instance_namespace=resolve_instance_namespace(self.bootstrap),
                    queue=settings.celery.scene_git_queue,
                    publish_timeout_seconds=settings.celery.publish_timeout_seconds,
                )
                dispatcher = self._owned_scene_git_dispatcher
            shared_scene_repository = MysqlSharedSceneAssetRepository(sessions)
            scene_git_repository = MysqlWorkspaceSceneGitRepository(
                sessions,
                scene_assets=shared_scene_repository,
            )
            scene_git_service = SceneGitAdminService(
                org_repository=self._iam.admin_org_repository,
                asset_repository=shared_scene_repository,
                git_repository=git_repository,
                scene_git_repository=scene_git_repository,
                workspace_repository=workspace_repository,
                job_repository=MysqlBackgroundJobRepository(sessions),
                dispatcher=dispatcher,
            )
            self.scene_service = ZhizhiAssetAdminService(
                kind="scene",
                repository=workspace_repository,
                assets=shared_asset_repository,
                org_repository=self._iam.admin_org_repository,
                scene_git_service=scene_git_service,
            )
        self._previous_filesystem_scan_recorder = install_zhizhi_filesystem_metrics()
        self._started = True

    async def shutdown(self) -> None:
        self._started = False
        previous_recorder = self._previous_filesystem_scan_recorder
        self._previous_filesystem_scan_recorder = None
        if previous_recorder is not None:
            configure_filesystem_scan_recorder(previous_recorder)
        self.auth_service = None
        self.bootstrap_service = None
        self.admin_user_service = None
        self.role_service = None
        self.organization_service = None
        self.tenant_member_service = None
        self.git_service = None
        self.llm_service = None
        self.data_source_service = None
        self.skill_service = None
        self.scene_service = None
        self.audit_writer = None
        if self._owned_scene_git_dispatcher is not None:
            self._owned_scene_git_dispatcher.close()
            self._owned_scene_git_dispatcher = None
        if self._iam is not None:
            await self._iam.shutdown()
            self._iam = None
        if self._database is not None:
            await self._database.shutdown()
            self._database = None
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
        if self._http is not None:
            await self._http.shutdown()
            self._http = None

    def readiness_snapshot(self) -> RuntimeReadinessSnapshot:
        if not self._started or self._http is None or self._database is None or self._iam is None:
            return RuntimeReadinessSnapshot(ready=False, reasons=("process_not_started",))
        snapshot = self._http.readiness_snapshot()
        reasons = list(snapshot.reasons)
        if not self._iam.started:
            reasons.append("iam_not_started")
        if not self._database.started:
            reasons.append("database_not_started")
        if self._redis is None or not self._redis.initialized:
            reasons.append("redis_not_started")
        return RuntimeReadinessSnapshot(ready=not reasons, reasons=tuple(reasons))
