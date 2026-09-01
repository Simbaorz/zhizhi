"""Zhizhi model catalog, entitlement, binding, and connectivity use cases."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from gewu_core import ApplicationError, ApplicationErrorKind, utc_now
from zhizhi_platform.iam import (
    AdminSessionUser,
    ensure_admin_permission,
    ensure_super_admin,
    permission_view_scopes,
)
from zhizhi_platform.llm.domain import (
    ManagedLLMBinding,
    ManagedLLMConfig,
    ManagedLLMEntitlement,
)
from zhizhi_platform.llm.policy import (
    ACTIVE_STATUS,
    CONFIGURED_CREDENTIAL_STATUS,
    INACTIVE_STATUS,
    binding_admin_scope,
    clean_required,
    decrypt_credentials,
    ensure_active_entitlement,
    ensure_entitlement_not_in_use,
    ensure_no_active_allocations,
    ensure_no_allocations,
    ensure_parent_entitlement,
    llm_secret_values,
    normalize_credentials,
    normalize_provider_config,
    public_binding,
    public_config,
    public_entitlement,
    require_binding,
    require_config,
    require_entitlement,
    require_parent_entitlement_permission,
    require_scoped_permission,
    safe_error_message,
    scoped_config,
    stable_code,
    validate_binding_model,
    validate_binding_scope,
    validate_binding_target,
    validate_common_config,
    validate_credentials,
    validate_generation_config,
    validate_provider_config,
    validate_runtime_overrides,
    validate_status,
)
from zhizhi_platform.llm.ports import (
    LLMAdminRepository,
    LLMConnectivityRequest,
    LLMConnectivityTester,
    LLMCredentialCipher,
    LLMPage,
    ZhizhiLLMOrganizationDirectory,
)


class LLMModelPage(BaseModel):
    """One paged model list produced by the catalog handler."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, object], ...] = ()
    total: int = Field(default=0, ge=0)


class CreateLLMConfigCommand(BaseModel):
    """Create one global model configuration."""

    model_config = ConfigDict(frozen=True)

    alias: str
    display_name: str = ""
    provider: str
    protocol: str
    model_name: str
    endpoint_url: str = ""
    status: str = "active"
    support_stream: bool = True
    support_tools: bool = True
    support_vision: bool = False
    support_thinking: bool = False
    timeout_seconds: int = 600
    generation_config: dict[str, Any] = Field(default_factory=dict)
    provider_config: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] = Field(default_factory=dict)


class UpdateLLMConfigCommand(BaseModel):
    """Patch one global model configuration."""

    model_config = ConfigDict(frozen=True)

    display_name: str | None = None
    model_name: str | None = None
    endpoint_url: str | None = None
    status: str | None = None
    support_stream: bool | None = None
    support_tools: bool | None = None
    support_vision: bool | None = None
    support_thinking: bool | None = None
    timeout_seconds: int | None = None
    generation_config: dict[str, Any] | None = None
    provider_config: dict[str, Any] | None = None


class CreateLLMEntitlementCommand(BaseModel):
    """Create one model-pool entitlement."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    scope_type: str
    organization_unit_id: str = ""
    llm_config_id: str
    status: str = "active"


class CreateLLMEntitlementsCommand(BaseModel):
    """Create several model-pool entitlements."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    scope_type: str
    organization_unit_id: str = ""
    llm_config_ids: list[str]
    status: str = "active"


class CreateLLMBindingCommand(BaseModel):
    """Create one effective model binding."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    scope_type: str
    organization_unit_id: str = ""
    llm_config_id: str
    status: str = "active"
    runtime_overrides: dict[str, Any] = Field(default_factory=dict)


class UpdateLLMBindingCommand(BaseModel):
    """Patch one effective model binding."""

    model_config = ConfigDict(frozen=True)

    llm_config_id: str | None = None
    status: str | None = None
    runtime_overrides: dict[str, Any] | None = None


class ZhizhiLLMAdminService:
    """Execute exact Zhizhi model-management behavior outside Agent Runtime."""

    def __init__(
        self,
        *,
        repository: LLMAdminRepository,
        org_repository: ZhizhiLLMOrganizationDirectory,
        connectivity_tester: LLMConnectivityTester,
        cipher: LLMCredentialCipher,
    ) -> None:
        self._repository = repository
        self._org_repository = org_repository
        self._connectivity_tester = connectivity_tester
        self._cipher = cipher

    async def list_models(
        self,
        session_user: AdminSessionUser,
        *,
        tenant_id: str | None,
        search: str,
        status: str,
        provider: str,
        page: int,
        page_size: int,
    ) -> LLMModelPage:
        if tenant_id is None:
            ensure_super_admin(session_user)
            result = await self._repository.list_configs_page(
                page=page,
                page_size=page_size,
                search=search,
                status=status,
                provider=provider,
            )
            converter = public_config
        else:
            ensure_admin_permission(session_user, "llm.view")
            view_scopes = permission_view_scopes(session_user, "llm.view")
            if view_scopes is not None:
                tenant_scopes = tuple(
                    scope for scope in view_scopes if scope.scope_tenant_id == tenant_id
                )
                if not tenant_scopes:
                    raise ApplicationError(
                        ApplicationErrorKind.FORBIDDEN,
                        "Missing tenant-scoped model view permission.",
                    )
            else:
                tenant_scopes = None
            result = await self._repository.list_configs_page(
                page=page,
                page_size=page_size,
                search=search,
                status=status,
                provider=provider,
                tenant_id=None if session_user.is_super else tenant_id,
                view_scopes=None if session_user.is_super else tenant_scopes,
                include_endpoint_in_search=False,
            )
            converter = public_config if session_user.is_super else scoped_config
        return LLMModelPage(
            items=tuple(converter(row, self._cipher) for row in result.items),
            total=result.total,
        )

    async def create_config(
        self,
        session_user: AdminSessionUser,
        command: CreateLLMConfigCommand,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        alias = clean_required(command.alias, "模型别名不能为空。")
        if await self._repository.get_config_by_alias(alias) is not None:
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "模型别名已存在。")
        validate_common_config(
            command.provider,
            command.protocol,
            command.model_name,
            command.endpoint_url,
            command.status,
            command.timeout_seconds,
        )
        provider_config = normalize_provider_config(command.provider, command.provider_config)
        validate_provider_config(command.provider, provider_config)
        credentials = normalize_credentials(command.provider, command.credentials)
        validate_credentials(command.provider, credentials)
        generation_config = validate_generation_config(command.generation_config)
        saved = await self._repository.save_config(
            ManagedLLMConfig(
                alias=alias,
                display_name=command.display_name.strip() or alias,
                provider=command.provider,
                protocol=command.protocol,
                model_name=command.model_name.strip(),
                endpoint_url=command.endpoint_url.strip(),
                status=command.status,
                support_stream=command.support_stream,
                support_tools=command.support_tools,
                support_vision=command.support_vision,
                support_thinking=command.support_thinking,
                timeout_seconds=command.timeout_seconds,
                generation_config=generation_config,
                provider_config=provider_config,
                credentials_ciphertext=self._cipher.encrypt(credentials),
                credential_status=CONFIGURED_CREDENTIAL_STATUS,
            )
        )
        return public_config(saved, self._cipher)

    async def update_config(
        self,
        session_user: AdminSessionUser,
        model_id: str,
        command: UpdateLLMConfigCommand,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        config = await require_config(model_id, self._repository)
        next_status = command.status if command.status is not None else config.status
        if next_status == INACTIVE_STATUS:
            await ensure_no_active_allocations(model_id, self._repository)
        next_model_name = (
            command.model_name.strip() if command.model_name is not None else config.model_name
        )
        next_endpoint_url = (
            command.endpoint_url.strip()
            if command.endpoint_url is not None
            else config.endpoint_url
        )
        next_timeout = (
            command.timeout_seconds
            if command.timeout_seconds is not None
            else config.timeout_seconds
        )
        next_provider_config = (
            dict(command.provider_config)
            if command.provider_config is not None
            else dict(config.provider_config)
        )
        next_provider_config = normalize_provider_config(config.provider, next_provider_config)
        next_generation_config = (
            validate_generation_config(command.generation_config)
            if command.generation_config is not None
            else dict(config.generation_config)
        )
        validate_common_config(
            config.provider,
            config.protocol,
            next_model_name,
            next_endpoint_url,
            next_status,
            next_timeout,
        )
        validate_provider_config(config.provider, next_provider_config)
        saved = await self._repository.save_config(
            config.model_copy(
                update={
                    "display_name": (
                        command.display_name.strip()
                        if command.display_name is not None and command.display_name.strip()
                        else config.display_name
                    ),
                    "model_name": next_model_name,
                    "endpoint_url": next_endpoint_url,
                    "status": next_status,
                    "support_stream": (
                        command.support_stream
                        if command.support_stream is not None
                        else config.support_stream
                    ),
                    "support_tools": (
                        command.support_tools
                        if command.support_tools is not None
                        else config.support_tools
                    ),
                    "support_vision": (
                        command.support_vision
                        if command.support_vision is not None
                        else config.support_vision
                    ),
                    "support_thinking": (
                        command.support_thinking
                        if command.support_thinking is not None
                        else config.support_thinking
                    ),
                    "timeout_seconds": next_timeout,
                    "generation_config": next_generation_config,
                    "provider_config": next_provider_config,
                }
            )
        )
        return public_config(saved, self._cipher)

    async def delete_config(
        self,
        session_user: AdminSessionUser,
        model_id: str,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        await require_config(model_id, self._repository)
        await ensure_no_allocations(model_id, self._repository)
        if not await self._repository.delete_config(model_id):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "模型配置不存在。")
        return {"deleted": True}

    async def update_credentials(
        self,
        session_user: AdminSessionUser,
        model_id: str,
        credentials: dict[str, Any],
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        config = await require_config(model_id, self._repository)
        existing = (
            decrypt_credentials(config, self._cipher) if config.credentials_ciphertext else {}
        )
        normalized = normalize_credentials(config.provider, {**existing, **credentials})
        validate_credentials(config.provider, normalized)
        saved = await self._repository.save_config(
            config.model_copy(
                update={
                    "credentials_ciphertext": self._cipher.encrypt(normalized),
                    "credential_status": CONFIGURED_CREDENTIAL_STATUS,
                }
            )
        )
        return public_config(saved, self._cipher)

    async def validate_config(
        self,
        session_user: AdminSessionUser,
        model_id: str,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        config = await require_config(model_id, self._repository)
        try:
            validate_common_config(
                config.provider,
                config.protocol,
                config.model_name,
                config.endpoint_url,
                config.status,
                config.timeout_seconds,
            )
            validate_provider_config(config.provider, config.provider_config)
            credentials = decrypt_credentials(config, self._cipher)
            validate_credentials(config.provider, credentials)
        except ApplicationError as exc:
            return {"ok": False, "message": exc.detail}
        return {"ok": True, "message": "配置校验通过。"}

    async def test_config(
        self,
        session_user: AdminSessionUser,
        model_id: str,
        *,
        prompt: str,
        system_prompt: str,
    ) -> dict[str, object]:
        ensure_super_admin(session_user)
        config = await require_config(model_id, self._repository)
        prompt = clean_required(prompt, "测试内容不能为空。")
        if config.status != ACTIVE_STATUS:
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "只有 active 模型可以测试。")
        validation = await self.validate_config(session_user, model_id)
        if not validation["ok"]:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                str(validation["message"]),
            )
        credentials = decrypt_credentials(config, self._cipher)
        started_at = time.perf_counter()
        try:
            connectivity_result = await self._connectivity_tester.test(
                LLMConnectivityRequest(
                    provider=config.provider,
                    model_name=config.model_name,
                    endpoint_url=config.endpoint_url,
                    timeout_seconds=config.timeout_seconds,
                    generation_config=config.generation_config,
                    provider_config=config.provider_config,
                    credentials=credentials,
                    prompt=prompt,
                    system_prompt=system_prompt,
                )
            )
            content = connectivity_result.content
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            await self._repository.update_test_result(
                model_id,
                status="success",
                message=content[:512] if content else "测试成功。",
                tested_at=utc_now(),
            )
            return {
                "ok": True,
                "content": content,
                "latency_ms": latency_ms,
                "usage": connectivity_result.usage,
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            error_message = safe_error_message(
                exc,
                secret_values=llm_secret_values(config, credentials),
            )
            await self._repository.update_test_result(
                model_id,
                status="failed",
                message=error_message,
                tested_at=utc_now(),
            )
            return {
                "ok": False,
                "content": "",
                "latency_ms": latency_ms,
                "usage": None,
                "error": error_message,
            }

    async def list_bindings(
        self,
        session_user: AdminSessionUser,
        *,
        tenant_id: str | None,
        search: str,
        status: str,
        scope_type: str,
        organization_unit_id: str,
        page: int,
        page_size: int,
    ) -> LLMPage:
        ensure_admin_permission(session_user, "llm.view")
        scope_filter = "all" if scope_type == "all" else validate_binding_scope(scope_type)
        result = await self._repository.list_bindings_page(
            page=page,
            page_size=page_size,
            tenant_id=tenant_id,
            search=search,
            status=status,
            scope_type=scope_filter,
            organization_unit_id=organization_unit_id,
            view_scopes=permission_view_scopes(session_user, "llm.view"),
        )
        return LLMPage(
            items=tuple(public_binding(binding) for binding in result.items),
            total=result.total,
        )

    async def list_entitlements(
        self,
        session_user: AdminSessionUser,
        *,
        tenant_id: str | None,
        search: str,
        status: str,
        scope_type: str,
        organization_unit_id: str,
        page: int,
        page_size: int,
    ) -> LLMPage:
        ensure_admin_permission(session_user, "llm.view")
        scope_filter = "all" if scope_type == "all" else validate_binding_scope(scope_type)
        result = await self._repository.list_entitlements_page(
            page=page,
            page_size=page_size,
            tenant_id=tenant_id,
            search=search,
            status=status,
            scope_type=scope_filter,
            organization_unit_id=organization_unit_id,
            view_scopes=permission_view_scopes(session_user, "llm.view"),
        )
        return LLMPage(
            items=tuple(public_entitlement(item) for item in result.items),
            total=result.total,
        )

    async def create_entitlement(
        self,
        command: CreateLLMEntitlementCommand,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "llm.bindings.edit")
        tenant_id, scope_type, organization_unit_id = await self._entitlement_target(
            session_user,
            command.tenant_id,
            command.scope_type,
            command.organization_unit_id,
        )
        if await self._repository.get_entitlement_by_scope_model(
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
            llm_config_id=command.llm_config_id,
        ):
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "该范围已拥有该模型。")
        entitlement_status = validate_status(command.status)
        await validate_binding_model(command.llm_config_id, entitlement_status, self._repository)
        await ensure_parent_entitlement(
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
            llm_config_id=command.llm_config_id,
            repository=self._repository,
            org_repository=self._org_repository,
        )
        saved = await self._repository.save_entitlement(
            ManagedLLMEntitlement(
                tenant_id=tenant_id,
                scope_type=scope_type,
                organization_unit_id=organization_unit_id,
                llm_config_id=command.llm_config_id,
                status=entitlement_status,
            )
        )
        return public_entitlement(saved)

    async def create_entitlements(
        self,
        command: CreateLLMEntitlementsCommand,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "llm.bindings.edit")
        if len(command.llm_config_ids) > 10:
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "一次最多分配 10 个模型。")
        if not command.llm_config_ids:
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "至少选择一个模型。")
        if len(set(command.llm_config_ids)) != len(command.llm_config_ids):
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "不能重复选择同一个模型。")
        tenant_id, scope_type, organization_unit_id = await self._entitlement_target(
            session_user,
            command.tenant_id,
            command.scope_type,
            command.organization_unit_id,
        )
        entitlement_status = validate_status(command.status)
        for config_id in command.llm_config_ids:
            if await self._repository.get_entitlement_by_scope_model(
                tenant_id=tenant_id,
                scope_type=scope_type,
                organization_unit_id=organization_unit_id,
                llm_config_id=config_id,
            ):
                raise ApplicationError(ApplicationErrorKind.CONFLICT, "该范围已拥有所选模型。")
            await validate_binding_model(config_id, entitlement_status, self._repository)
            await ensure_parent_entitlement(
                tenant_id=tenant_id,
                scope_type=scope_type,
                organization_unit_id=organization_unit_id,
                llm_config_id=config_id,
                repository=self._repository,
                org_repository=self._org_repository,
            )
        saved = await self._repository.save_entitlements(
            tuple(
                ManagedLLMEntitlement(
                    tenant_id=tenant_id,
                    scope_type=scope_type,
                    organization_unit_id=organization_unit_id,
                    llm_config_id=config_id,
                    status=entitlement_status,
                )
                for config_id in command.llm_config_ids
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
        ensure_admin_permission(session_user, "llm.bindings.edit")
        entitlement = await require_entitlement(entitlement_id, self._repository)
        scope = await binding_admin_scope(
            tenant_id=entitlement.tenant_id,
            scope_type=entitlement.scope_type,
            organization_unit_id=entitlement.organization_unit_id,
            org_repository=self._org_repository,
        )
        require_parent_entitlement_permission(session_user, "llm.bindings.edit", scope)
        next_status = validate_status(status) if status is not None else entitlement.status
        await validate_binding_model(entitlement.llm_config_id, next_status, self._repository)
        if next_status == ACTIVE_STATUS:
            await ensure_parent_entitlement(
                tenant_id=entitlement.tenant_id,
                scope_type=entitlement.scope_type,
                organization_unit_id=entitlement.organization_unit_id,
                llm_config_id=entitlement.llm_config_id,
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
        ensure_admin_permission(session_user, "llm.bindings.edit")
        entitlement = await require_entitlement(entitlement_id, self._repository)
        scope = await binding_admin_scope(
            tenant_id=entitlement.tenant_id,
            scope_type=entitlement.scope_type,
            organization_unit_id=entitlement.organization_unit_id,
            org_repository=self._org_repository,
        )
        require_parent_entitlement_permission(session_user, "llm.bindings.edit", scope)
        await ensure_entitlement_not_in_use(
            entitlement,
            self._repository,
            self._org_repository,
        )
        if not await self._repository.delete_entitlement(entitlement_id):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "模型可用池条目不存在。")
        return {"deleted": True}

    async def create_binding(
        self,
        command: CreateLLMBindingCommand,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "llm.bindings.edit")
        tenant_id = stable_code(command.tenant_id)
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
        require_scoped_permission(session_user, "llm.bindings.edit", scope)
        if await self._repository.get_binding_by_scope(
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
        ):
            raise ApplicationError(ApplicationErrorKind.CONFLICT, "该范围已绑定模型。")
        binding_status = validate_status(command.status)
        await validate_binding_model(command.llm_config_id, binding_status, self._repository)
        await ensure_active_entitlement(
            tenant_id=tenant_id,
            scope_type=scope_type,
            organization_unit_id=organization_unit_id,
            llm_config_id=command.llm_config_id,
            repository=self._repository,
        )
        overrides = validate_runtime_overrides(command.runtime_overrides)
        saved = await self._repository.save_binding(
            ManagedLLMBinding(
                tenant_id=tenant_id,
                scope_type=scope_type,
                organization_unit_id=organization_unit_id,
                llm_config_id=command.llm_config_id,
                status=binding_status,
                runtime_overrides=overrides,
            )
        )
        return public_binding(saved)

    async def update_binding(
        self,
        binding_id: str,
        command: UpdateLLMBindingCommand,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "llm.bindings.edit")
        binding = await require_binding(binding_id, self._repository)
        scope = await binding_admin_scope(
            tenant_id=binding.tenant_id,
            scope_type=binding.scope_type,
            organization_unit_id=binding.organization_unit_id,
            org_repository=self._org_repository,
        )
        require_scoped_permission(session_user, "llm.bindings.edit", scope)
        next_config_id = (
            command.llm_config_id if command.llm_config_id is not None else binding.llm_config_id
        )
        next_status = (
            validate_status(command.status) if command.status is not None else binding.status
        )
        await validate_binding_model(next_config_id, next_status, self._repository)
        if next_status == ACTIVE_STATUS:
            await ensure_active_entitlement(
                tenant_id=binding.tenant_id,
                scope_type=binding.scope_type,
                organization_unit_id=binding.organization_unit_id,
                llm_config_id=next_config_id,
                repository=self._repository,
            )
        next_overrides = (
            validate_runtime_overrides(command.runtime_overrides)
            if command.runtime_overrides is not None
            else dict(binding.runtime_overrides)
        )
        saved = await self._repository.save_binding(
            binding.model_copy(
                update={
                    "llm_config_id": next_config_id,
                    "status": next_status,
                    "runtime_overrides": next_overrides,
                }
            )
        )
        return public_binding(saved)

    async def delete_binding(
        self,
        binding_id: str,
        session_user: AdminSessionUser,
    ) -> dict[str, object]:
        ensure_admin_permission(session_user, "llm.bindings.edit")
        binding = await require_binding(binding_id, self._repository)
        scope = await binding_admin_scope(
            tenant_id=binding.tenant_id,
            scope_type=binding.scope_type,
            organization_unit_id=binding.organization_unit_id,
            org_repository=self._org_repository,
        )
        require_scoped_permission(session_user, "llm.bindings.edit", scope)
        if not await self._repository.delete_binding(binding_id):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "模型绑定不存在。")
        return {"deleted": True}

    async def _entitlement_target(
        self,
        session_user: AdminSessionUser,
        tenant_id: str,
        scope_type: str,
        organization_unit_id: str,
    ) -> tuple[str, str, str]:
        normalized_tenant_id = stable_code(tenant_id)
        normalized_scope_type = validate_binding_scope(scope_type)
        normalized_organization_unit_id = await validate_binding_target(
            tenant_id=normalized_tenant_id,
            scope_type=normalized_scope_type,
            organization_unit_id=organization_unit_id,
            org_repository=self._org_repository,
        )
        scope = await binding_admin_scope(
            tenant_id=normalized_tenant_id,
            scope_type=normalized_scope_type,
            organization_unit_id=normalized_organization_unit_id,
            org_repository=self._org_repository,
        )
        require_parent_entitlement_permission(session_user, "llm.bindings.edit", scope)
        return (
            normalized_tenant_id,
            normalized_scope_type,
            normalized_organization_unit_id,
        )
