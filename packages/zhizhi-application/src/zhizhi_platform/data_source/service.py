"""致知 Data Source catalog, entitlement, and binding use cases."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from gewu_core import ApplicationError, ApplicationErrorKind
from zhizhi_platform.data_source.domain import (
    ManagedDataSourceSource,
    ManagedDataSourceSourceBinding,
    ManagedDataSourceSourceEntitlement,
)
from zhizhi_platform.data_source.policy import (
    ACTIVE_STATUS,
    CONFIGURED_CREDENTIAL_STATUS,
    INACTIVE_STATUS,
    binding_admin_scope,
    decrypt_credentials,
    ensure_active_entitlement,
    ensure_entitlement_not_in_use,
    ensure_no_active_allocations,
    ensure_no_allocations,
    ensure_parent_entitlement,
    normalize_credentials,
    public_binding,
    public_entitlement,
    public_source,
    require_binding,
    require_entitlement,
    require_parent_entitlement_permission,
    require_scoped_permission,
    require_source,
    stable_code,
    validate_binding_scope,
    validate_binding_source,
    validate_binding_target,
    validate_credentials,
    validate_source_config,
    validate_status,
)
from zhizhi_platform.data_source.ports import (
    DataSourceAdminRepository,
    DataSourceCredentialCipher,
    DataSourcePage,
    ZhizhiDataSourceOrganizationDirectory,
)
from zhizhi_platform.iam import (
    AdminSessionUser,
    ensure_admin_permission,
    ensure_super_admin,
    permission_view_scopes,
)


class DataSourceSourcePage(BaseModel):
    """One page from the global Data Source source catalog."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, object], ...] = ()
    total: int = Field(default=0, ge=0)


class CreateDataSourceSourceCommand(BaseModel):
    """Create one Data Source source."""

    model_config = ConfigDict(frozen=True)

    source_key: str
    display_name: str = ""
    description: str = ""
    status: str = "active"
    api_url: str
    app_id: str
    app_key: str
    app_secret: str
    default_database_key: str
    exec_sources_code: str
    timeout_seconds: int = 30
    default_max_rows: int = 50
    hard_max_rows: int = 500
    allow_databases: str = ""
    log_sql: bool = False


class UpdateDataSourceSourceCommand(BaseModel):
    """Patch one Data Source source."""

    model_config = ConfigDict(frozen=True)

    display_name: str | None = None
    description: str | None = None
    status: str | None = None
    api_url: str | None = None
    app_id: str | None = None
    app_key: str | None = None
    app_secret: str | None = None
    default_database_key: str | None = None
    exec_sources_code: str | None = None
    timeout_seconds: int | None = None
    default_max_rows: int | None = None
    hard_max_rows: int | None = None
    allow_databases: str | None = None
    log_sql: bool | None = None


class CreateDataSourceEntitlementCommand(BaseModel):
    """Create source-pool entitlements for one 致知 scope."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    scope_type: str
    organization_unit_id: str = ""
    data_source_ids: list[str]
    status: str = "active"


class CreateDataSourceBindingCommand(BaseModel):
    """Bind one Data Source source to a tenant or organization unit."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    scope_type: str
    organization_unit_id: str = ""
    data_source_id: str
    status: str = "active"


class ZhizhiDataSourceAdminService:
    """Execute exact 致知 Data Source management behavior outside Runtime."""

    def __init__(
        self,
        *,
        repository: DataSourceAdminRepository,
        org_repository: ZhizhiDataSourceOrganizationDirectory,
        cipher: DataSourceCredentialCipher,
    ) -> None:
        self._repository = repository
        self._org_repository = org_repository
        self._cipher = cipher

    async def list_sources(
        self,
        session_user: AdminSessionUser,
        *,
        search: str,
        status: str,
        page: int,
        page_size: int,
    ) -> DataSourceSourcePage:
        """List one SQL-filtered page of global sources."""

        ensure_admin_permission(session_user, "data_source.view")
        sources = await self._repository.list_sources_page(
            page=page,
            page_size=page_size,
            search=search,
            status=status,
        )
        return DataSourceSourcePage(
            items=tuple(public_source(source, self._cipher) for source in sources.items),
            total=sources.total,
        )

    async def create_source(
        self,
        session_user: AdminSessionUser,
        command: CreateDataSourceSourceCommand,
    ) -> dict[str, object]:
        """Create one global source."""

        ensure_super_admin(session_user)
        source_key = stable_code(command.source_key, "数据源编码")
        if await self._repository.get_source_by_key(source_key) is not None:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "数据源编码已存在。")
        status = validate_status(command.status)
        validate_source_config(
            api_url=command.api_url,
            app_id=command.app_id,
            default_database_key=command.default_database_key,
            exec_sources_code=command.exec_sources_code,
            timeout_seconds=command.timeout_seconds,
            default_max_rows=command.default_max_rows,
            hard_max_rows=command.hard_max_rows,
        )
        credentials = normalize_credentials(
            {"app_key": command.app_key, "app_secret": command.app_secret}
        )
        validate_credentials(credentials)
        saved = await self._repository.save_source(
            ManagedDataSourceSource(
                source_key=source_key,
                display_name=command.display_name.strip() or source_key,
                description=command.description.strip(),
                status=status,
                api_url=command.api_url.strip(),
                app_id=str(command.app_id).strip(),
                credentials_ciphertext=self._cipher.encrypt(credentials),
                credential_status=CONFIGURED_CREDENTIAL_STATUS,
                default_database_key=command.default_database_key.strip(),
                exec_sources_code=command.exec_sources_code.strip(),
                timeout_seconds=command.timeout_seconds,
                default_max_rows=command.default_max_rows,
                hard_max_rows=command.hard_max_rows,
                allow_databases=command.allow_databases.strip(),
                log_sql=command.log_sql,
            )
        )
        return public_source(saved, self._cipher)

    async def update_source(
        self,
        session_user: AdminSessionUser,
        source_id: str,
        command: UpdateDataSourceSourceCommand,
    ) -> dict[str, object]:
        """Patch one global source."""

        ensure_super_admin(session_user)
        source = await require_source(source_id, self._repository)
        next_status = (
            validate_status(command.status) if command.status is not None else source.status
        )
        if next_status == INACTIVE_STATUS:
            await ensure_no_active_allocations(source_id, self._repository)
        existing_credentials = (
            decrypt_credentials(source, self._cipher) if source.credentials_ciphertext else {}
        )
        next_credentials = normalize_credentials(
            {
                **existing_credentials,
                **({"app_key": command.app_key} if command.app_key is not None else {}),
                **({"app_secret": command.app_secret} if command.app_secret is not None else {}),
            }
        )
        credential_status = source.credential_status
        credentials_ciphertext = source.credentials_ciphertext
        if command.app_key is not None or command.app_secret is not None:
            validate_credentials(next_credentials)
            credential_status = CONFIGURED_CREDENTIAL_STATUS
            credentials_ciphertext = self._cipher.encrypt(next_credentials)
        next_api_url = command.api_url.strip() if command.api_url is not None else source.api_url
        next_app_id = str(command.app_id).strip() if command.app_id is not None else source.app_id
        next_database = (
            command.default_database_key.strip()
            if command.default_database_key is not None
            else source.default_database_key
        )
        next_exec_source = (
            command.exec_sources_code.strip()
            if command.exec_sources_code is not None
            else source.exec_sources_code
        )
        next_timeout = (
            command.timeout_seconds
            if command.timeout_seconds is not None
            else source.timeout_seconds
        )
        next_default_rows = (
            command.default_max_rows
            if command.default_max_rows is not None
            else source.default_max_rows
        )
        next_hard_rows = (
            command.hard_max_rows if command.hard_max_rows is not None else source.hard_max_rows
        )
        validate_source_config(
            api_url=next_api_url,
            app_id=next_app_id,
            default_database_key=next_database,
            exec_sources_code=next_exec_source,
            timeout_seconds=next_timeout,
            default_max_rows=next_default_rows,
            hard_max_rows=next_hard_rows,
        )
        saved = await self._repository.save_source(
            source.model_copy(
                update={
                    "display_name": (
                        command.display_name.strip()
                        if command.display_name is not None and command.display_name.strip()
                        else source.display_name
                    ),
                    "description": (
                        command.description.strip()
                        if command.description is not None
                        else source.description
                    ),
                    "status": next_status,
                    "api_url": next_api_url,
                    "app_id": next_app_id,
                    "credentials_ciphertext": credentials_ciphertext,
                    "credential_status": credential_status,
                    "default_database_key": next_database,
                    "exec_sources_code": next_exec_source,
                    "timeout_seconds": next_timeout,
                    "default_max_rows": next_default_rows,
                    "hard_max_rows": next_hard_rows,
                    "allow_databases": (
                        command.allow_databases.strip()
                        if command.allow_databases is not None
                        else source.allow_databases
                    ),
                    "log_sql": command.log_sql if command.log_sql is not None else source.log_sql,
                }
            )
        )
        return public_source(saved, self._cipher)

    async def delete_source(
        self,
        session_user: AdminSessionUser,
        source_id: str,
    ) -> dict[str, object]:
        """Delete one source only when no allocation references it."""

        ensure_super_admin(session_user)
        await require_source(source_id, self._repository)
        await ensure_no_allocations(source_id, self._repository)
        if not await self._repository.delete_source(source_id):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "数据源不存在。")
        return {"deleted": True}

    async def list_bindings(
        self,
        session_user: AdminSessionUser,
        *,
        tenant_id: str | None,
        scope_type: str,
        organization_unit_id: str,
        search: str,
        status: str,
        page: int,
        page_size: int,
    ) -> DataSourcePage:
        """List authorized effective bindings."""

        ensure_admin_permission(session_user, "data_source.view")
        result = await self._repository.list_bindings_page(
            page=page,
            page_size=page_size,
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
            search=search,
            status=status,
            view_scopes=permission_view_scopes(session_user, "data_source.view"),
        )
        return DataSourcePage(
            items=tuple(public_binding(binding) for binding in result.items),
            total=result.total,
        )

    async def list_entitlements(
        self,
        session_user: AdminSessionUser,
        *,
        tenant_id: str | None,
        scope_type: str,
        organization_unit_id: str,
        search: str,
        status: str,
        page: int,
        page_size: int,
    ) -> DataSourcePage:
        """List authorized source-pool entries for organization scopes."""

        ensure_admin_permission(session_user, "data_source.view")
        scope_filter = "all" if scope_type == "all" else validate_binding_scope(scope_type)
        result = await self._repository.list_entitlements_page(
            page=page,
            page_size=page_size,
            tenant_id=tenant_id,
            scope_type=scope_filter,
            organization_unit_id=organization_unit_id,
            search=search,
            status=status,
            view_scopes=permission_view_scopes(session_user, "data_source.view"),
        )
        return DataSourcePage(
            items=tuple(public_entitlement(item) for item in result.items),
            total=result.total,
        )

    async def create_entitlement(
        self,
        command: CreateDataSourceEntitlementCommand,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        """Create up to ten source-pool entries for one scope."""

        ensure_admin_permission(session_user, "data_source.bindings.edit")
        data_source_ids = command.data_source_ids
        if not data_source_ids or len(data_source_ids) > 10:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "一次最多分配 10 个数据源。",
            )
        if any(not data_source_id.strip() for data_source_id in data_source_ids):
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "数据源 ID 必须大于 0。",
            )
        if len(set(data_source_ids)) != len(data_source_ids):
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "不能重复选择数据源。",
            )
        tenant_id = stable_code(command.tenant_id, "租户编码")
        scope_type = validate_binding_scope(command.scope_type)
        organization_unit_id = await validate_binding_target(
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=command.organization_unit_id,
            org_repository=self._org_repository,
        )
        scope = await binding_admin_scope(
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
            org_repository=self._org_repository,
        )
        require_parent_entitlement_permission(
            session_user,
            "data_source.bindings.edit",
            scope,
        )
        entitlement_status = validate_status(command.status)
        for data_source_id in data_source_ids:
            if await self._repository.get_entitlement_by_scope_source(
                tenant_id=tenant_id,
                scope_type=scope_type,
                organization_unit_id=organization_unit_id,
                data_source_id=data_source_id,
            ):
                raise ApplicationError(
                    ApplicationErrorKind.CONFLICT,
                    "该范围已拥有所选数据源。",
                )
            await validate_binding_source(
                data_source_id,
                entitlement_status,
                self._repository,
            )
            await ensure_parent_entitlement(
                tenant_id=tenant_id,
                scope_type=scope_type,
                organization_unit_id=organization_unit_id,
                data_source_id=data_source_id,
                repository=self._repository,
                org_repository=self._org_repository,
            )
        saved = await self._repository.save_entitlements(
            tuple(
                ManagedDataSourceSourceEntitlement(
                    tenant_id=tenant_id,
                    scope_type=scope_type,
                    organization_unit_id=organization_unit_id,
                    data_source_id=data_source_id,
                    status=entitlement_status,
                )
                for data_source_id in data_source_ids
            )
        )
        return {"entitlements": [public_entitlement(item) for item in saved]}

    async def update_entitlement(
        self,
        entitlement_id: str,
        *,
        status: str | None,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        """Patch one source-pool entry."""

        ensure_admin_permission(session_user, "data_source.bindings.edit")
        entitlement = await require_entitlement(entitlement_id, self._repository)
        scope = await binding_admin_scope(
            tenant_id=entitlement.tenant_id,
            scope_type=entitlement.scope_type,
            organization_unit_id=entitlement.organization_unit_id,
            org_repository=self._org_repository,
        )
        require_parent_entitlement_permission(
            session_user,
            "data_source.bindings.edit",
            scope,
        )
        next_status = validate_status(status) if status is not None else entitlement.status
        await validate_binding_source(
            entitlement.data_source_id,
            next_status,
            self._repository,
        )
        if next_status == ACTIVE_STATUS:
            await ensure_parent_entitlement(
                tenant_id=entitlement.tenant_id,
                scope_type=entitlement.scope_type,
                organization_unit_id=entitlement.organization_unit_id,
                data_source_id=entitlement.data_source_id,
                repository=self._repository,
                org_repository=self._org_repository,
            )
        elif entitlement.status == ACTIVE_STATUS:
            await ensure_entitlement_not_in_use(
                entitlement,
                self._repository,
                self._org_repository,
            )
        saved = await self._repository.save_entitlement(
            entitlement.model_copy(update={"status": next_status})
        )
        return public_entitlement(saved)

    async def delete_entitlement(
        self,
        entitlement_id: str,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        """Delete one source-pool entry."""

        ensure_admin_permission(session_user, "data_source.bindings.edit")
        entitlement = await require_entitlement(entitlement_id, self._repository)
        scope = await binding_admin_scope(
            tenant_id=entitlement.tenant_id,
            scope_type=entitlement.scope_type,
            organization_unit_id=entitlement.organization_unit_id,
            org_repository=self._org_repository,
        )
        require_parent_entitlement_permission(
            session_user,
            "data_source.bindings.edit",
            scope,
        )
        await ensure_entitlement_not_in_use(
            entitlement,
            self._repository,
            self._org_repository,
        )
        if not await self._repository.delete_entitlement(entitlement_id):
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND,
                "数据源可用池条目不存在。",
            )
        return {"deleted": True}

    async def create_binding(
        self,
        command: CreateDataSourceBindingCommand,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        """Create one tenant or organization-unit source binding."""

        ensure_admin_permission(session_user, "data_source.bindings.edit")
        tenant_id = stable_code(command.tenant_id, "租户编码")
        scope_type = validate_binding_scope(command.scope_type)
        organization_unit_id = await validate_binding_target(
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=command.organization_unit_id,
            org_repository=self._org_repository,
        )
        scope = await binding_admin_scope(
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
            org_repository=self._org_repository,
        )
        require_scoped_permission(session_user, "data_source.bindings.edit", scope)
        if await self._repository.get_binding_by_scope(
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
        ):
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "该范围已绑定数据源。")
        binding_status = validate_status(command.status)
        await validate_binding_source(
            command.data_source_id,
            binding_status,
            self._repository,
        )
        await ensure_active_entitlement(
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
            data_source_id=command.data_source_id,
            repository=self._repository,
        )
        saved = await self._repository.save_binding(
            ManagedDataSourceSourceBinding(
                tenant_id=tenant_id,
                scope_type=scope_type,
                organization_unit_id=organization_unit_id,
                data_source_id=command.data_source_id,
                status=binding_status,
            )
        )
        return public_binding(saved)

    async def update_binding(
        self,
        binding_id: str,
        *,
        status: str | None,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        """Patch one source binding."""

        ensure_admin_permission(session_user, "data_source.bindings.edit")
        binding = await require_binding(binding_id, self._repository)
        scope = await binding_admin_scope(
            tenant_id=binding.tenant_id,
            scope_type=binding.scope_type,
            organization_unit_id=binding.organization_unit_id,
            org_repository=self._org_repository,
        )
        require_scoped_permission(session_user, "data_source.bindings.edit", scope)
        next_status = validate_status(status) if status is not None else binding.status
        if next_status == ACTIVE_STATUS:
            await validate_binding_source(
                binding.data_source_id,
                next_status,
                self._repository,
            )
            await ensure_active_entitlement(
                tenant_id=binding.tenant_id,
                scope_type=binding.scope_type,
                organization_unit_id=binding.organization_unit_id,
                data_source_id=binding.data_source_id,
                repository=self._repository,
            )
        saved = await self._repository.save_binding(
            binding.model_copy(update={"status": next_status})
        )
        return public_binding(saved)

    async def delete_binding(
        self,
        binding_id: str,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        """Delete one source binding."""

        ensure_admin_permission(session_user, "data_source.bindings.edit")
        binding = await require_binding(binding_id, self._repository)
        scope = await binding_admin_scope(
            tenant_id=binding.tenant_id,
            scope_type=binding.scope_type,
            organization_unit_id=binding.organization_unit_id,
            org_repository=self._org_repository,
        )
        require_scoped_permission(session_user, "data_source.bindings.edit", scope)
        if not await self._repository.delete_binding(binding_id):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "数据源绑定不存在。")
        return {"deleted": True}
