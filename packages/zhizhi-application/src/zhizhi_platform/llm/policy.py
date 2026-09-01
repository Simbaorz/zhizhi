"""Zhizhi model validation, hierarchy, authorization, and response projections."""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any
from urllib.parse import urlsplit

from gewu_core import ApplicationError, ApplicationErrorKind
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
    OrganizationUnitRef,
    has_admin_parent_scoped_permission,
    has_admin_scoped_permission,
)
from zhizhi_platform.llm.domain import (
    LLMProvider,
    ManagedLLMBinding,
    ManagedLLMConfig,
    ManagedLLMEntitlement,
    ModelProtocol,
)
from zhizhi_platform.llm.ports import (
    LLMAdminRepository,
    LLMConnectivityNetworkError,
    LLMConnectivityTimeoutError,
    LLMCredentialCipher,
    ZhizhiLLMOrganizationDirectory,
)

ACTIVE_STATUS = "active"
INACTIVE_STATUS = "inactive"
VALID_STATUSES = {ACTIVE_STATUS, INACTIVE_STATUS}
CONFIGURED_CREDENTIAL_STATUS = "configured"
PROVIDER_PROTOCOLS = {
    LLMProvider.OPENAI.value: ModelProtocol.OPENAI_CHAT.value,
    LLMProvider.ANTHROPIC.value: ModelProtocol.ANTHROPIC_MESSAGES.value,
    LLMProvider.UNICOM.value: ModelProtocol.CHINAUNICOM_OPEN_SERVICE.value,
}
RUNTIME_OVERRIDE_KEYS = {
    "stream",
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "seed",
}
DEFAULT_CONTEXT_WINDOW = 32768
BINDING_SCOPE_TENANT = "tenant"
BINDING_SCOPE_ORGANIZATION_UNIT = "organization_unit"
BINDING_SCOPES = {BINDING_SCOPE_TENANT, BINDING_SCOPE_ORGANIZATION_UNIT}


def validate_common_config(
    provider: str,
    protocol: str,
    model_name: str,
    endpoint_url: str,
    status: str,
    timeout_seconds: int,
) -> None:
    if provider not in PROVIDER_PROTOCOLS:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "模型来源不支持。")
    if protocol != PROVIDER_PROTOCOLS[provider]:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "模型来源与协议不匹配。")
    clean_required(model_name, "模型名称不能为空。")
    if provider != LLMProvider.OPENAI.value:
        clean_required(endpoint_url, "接口地址不能为空。")
    if endpoint_url.strip():
        validate_llm_endpoint_url(endpoint_url)
    validate_status(status)
    if timeout_seconds < 1 or timeout_seconds > 3600:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "超时时间必须在 1 到 3600 秒之间。",
        )


def validate_provider_config(provider: str, provider_config: dict[str, Any]) -> None:
    context_window(provider_config)
    if provider == LLMProvider.UNICOM.value:
        clean_required(_unicom_req_key(provider_config), "联通请求 Key 不能为空。")
        role_reflect = _role_reflect(provider_config)
        for role in ("system", "assistant", "user"):
            clean_required(role_reflect[role], "联通角色映射不完整。")


def normalize_provider_config(provider: str, provider_config: dict[str, Any]) -> dict[str, Any]:
    configured_context_window = context_window(provider_config)
    if provider != LLMProvider.UNICOM.value:
        return {**dict(provider_config), "context_window": configured_context_window}
    return {
        "context_window": configured_context_window,
        "req_key": _unicom_req_key(provider_config),
        "role_reflect": _role_reflect(provider_config),
        "chat_template_kwargs": _dict_value(provider_config.get("chat_template_kwargs")),
        "extra_headers": unicom_extra_headers(provider_config),
    }


def normalize_credentials(provider: str, credentials: dict[str, Any]) -> dict[str, str]:
    if provider in {LLMProvider.OPENAI.value, LLMProvider.ANTHROPIC.value}:
        return {"api_key": _credential_api_key(credentials)}
    if provider == LLMProvider.UNICOM.value:
        return {
            "app_id": _string_value(credentials.get("app_id")),
            "app_secret": _string_value(credentials.get("app_secret")),
            "nlpt_authorization": _nlpt_authorization(credentials),
        }
    return {}


def validate_credentials(provider: str, credentials: dict[str, Any]) -> None:
    if provider in {LLMProvider.OPENAI.value, LLMProvider.ANTHROPIC.value}:
        clean_required(_credential_api_key(credentials), "API Key 不能为空。")
        return
    if provider == LLMProvider.UNICOM.value:
        clean_required(_string_value(credentials.get("app_id")), "联通 APP_ID 不能为空。")
        clean_required(
            _string_value(credentials.get("app_secret")),
            "联通 APP_SECRET 不能为空。",
        )


def credential_fields(config: ManagedLLMConfig, cipher: LLMCredentialCipher) -> list[str]:
    if config.credential_status != CONFIGURED_CREDENTIAL_STATUS:
        return []
    try:
        credentials = decrypt_credentials(config, cipher)
    except ApplicationError:
        return []
    if config.provider in {LLMProvider.OPENAI.value, LLMProvider.ANTHROPIC.value}:
        return ["api_key"] if _credential_api_key(credentials) else []
    if config.provider == LLMProvider.UNICOM.value:
        fields = []
        if _string_value(credentials.get("app_id")):
            fields.append("app_id")
        if _string_value(credentials.get("app_secret")):
            fields.append("app_secret")
        if _nlpt_authorization(credentials):
            fields.append("nlpt_authorization")
        return fields
    return []


def decrypt_credentials(
    config: ManagedLLMConfig,
    cipher: LLMCredentialCipher,
) -> dict[str, Any]:
    try:
        return cipher.decrypt(config.credentials_ciphertext)
    except ValueError as exc:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "模型密钥无法解密，请重新配置密钥。",
        ) from exc


def validate_runtime_overrides(overrides: dict[str, Any]) -> dict[str, Any]:
    unexpected = sorted(set(overrides) - RUNTIME_OVERRIDE_KEYS)
    if unexpected:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            f"运行参数不支持：{', '.join(unexpected)}。",
        )
    cleaned: dict[str, Any] = {}
    if "stream" in overrides:
        value = overrides["stream"]
        if not isinstance(value, bool):
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "stream 必须是布尔值。")
        cleaned["stream"] = value
    for key in ("temperature", "top_p", "presence_penalty", "frequency_penalty"):
        if key in overrides:
            cleaned[key] = _bounded_number(key, overrides[key], minimum=-2, maximum=2)
    if "temperature" in cleaned:
        cleaned["temperature"] = _bounded_number("temperature", cleaned["temperature"], 0, 2)
    if "top_p" in cleaned:
        cleaned["top_p"] = _bounded_number("top_p", cleaned["top_p"], 0, 1)
    for key in ("max_tokens", "seed"):
        if key in overrides:
            cleaned[key] = _positive_int(key, overrides[key], allow_zero=key == "seed")
    return cleaned


def validate_generation_config(config: dict[str, Any]) -> dict[str, Any]:
    return validate_runtime_overrides(config)


def validate_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "状态必须是 active 或 inactive。",
        )
    return status


def clean_required(value: str, detail: str) -> str:
    text = value.strip()
    if not text:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, detail)
    return text


def safe_error_message(
    exc: Exception,
    *,
    secret_values: tuple[str, ...] = (),
) -> str:
    if isinstance(exc, ApplicationError):
        return _redact_secret_values(exc.detail, secret_values)[:512]
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status_code, int):
        return f"模型服务返回 HTTP {status_code}。"
    if isinstance(exc, LLMConnectivityTimeoutError):
        return "模型服务连接超时。"
    if isinstance(exc, LLMConnectivityNetworkError):
        return "模型服务连接失败。"
    return f"模型测试失败（{exc.__class__.__name__}）。"


def llm_secret_values(
    config: ManagedLLMConfig,
    credentials: dict[str, Any],
) -> tuple[str, ...]:
    values = [_string_value(value) for value in credentials.values()]
    values.extend(unicom_extra_headers(config.provider_config).values())
    return tuple(sorted({value for value in values if value}, key=len, reverse=True))


def validate_llm_endpoint_url(endpoint_url: str) -> None:
    try:
        parts = urlsplit(endpoint_url)
        _ = parts.port
    except ValueError as exc:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "模型接口地址无效。") from exc
    hostname = (parts.hostname or "").rstrip(".").lower()
    if parts.scheme.lower() not in {"http", "https"} or not hostname:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "模型接口只允许 HTTP 或 HTTPS 地址。",
        )
    if parts.username is not None or parts.password is not None or parts.fragment:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "模型接口地址不能包含凭据或片段。",
        )


def context_window(provider_config: dict[str, Any]) -> int:
    value = provider_config.get("context_window", DEFAULT_CONTEXT_WINDOW)
    if value is None or value == "":
        value = DEFAULT_CONTEXT_WINDOW
    return _positive_int("context_window", value)


def unicom_extra_headers(provider_config: dict[str, Any]) -> dict[str, str]:
    headers = _dict_string_values(provider_config.get("extra_headers"))
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in {"nlpt-authorization", "authorization"}
    }


async def require_config(config_id: str, repository: LLMAdminRepository) -> ManagedLLMConfig:
    config = await repository.get_config(config_id)
    if config is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "模型配置不存在。")
    return config


async def require_binding(binding_id: str, repository: LLMAdminRepository) -> ManagedLLMBinding:
    binding = await repository.get_binding(binding_id)
    if binding is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "模型绑定不存在。")
    return binding


async def require_entitlement(
    entitlement_id: str,
    repository: LLMAdminRepository,
) -> ManagedLLMEntitlement:
    entitlement = await repository.get_entitlement(entitlement_id)
    if entitlement is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "模型可用池条目不存在。")
    return entitlement


async def validate_binding_model(
    config_id: str,
    binding_status: str,
    repository: LLMAdminRepository,
) -> ManagedLLMConfig:
    config = await require_config(config_id, repository)
    if binding_status == ACTIVE_STATUS:
        if config.status != ACTIVE_STATUS:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "启用绑定必须选择 active 模型。",
            )
        if config.credential_status != CONFIGURED_CREDENTIAL_STATUS:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "启用绑定的模型必须已配置密钥。",
            )
    return config


async def ensure_no_active_allocations(
    config_id: str,
    repository: LLMAdminRepository,
) -> None:
    if await repository.binding_exists(llm_config_id=config_id, status=ACTIVE_STATUS):
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "模型仍存在启用绑定，不能停用。")
    if await repository.entitlement_exists(llm_config_id=config_id, status=ACTIVE_STATUS):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "模型仍存在启用可用池分配，不能停用。",
        )


async def ensure_no_allocations(config_id: str, repository: LLMAdminRepository) -> None:
    if await repository.binding_exists(llm_config_id=config_id):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "模型仍存在绑定关系，不能删除，请先解除模型绑定。",
        )
    if await repository.entitlement_exists(llm_config_id=config_id):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "模型仍存在可用池分配，不能删除，请先解除模型分配。",
        )


async def ensure_active_entitlement(
    *,
    tenant_id: str,
    scope_type: str,
    organization_unit_id: str,
    llm_config_id: str,
    repository: LLMAdminRepository,
) -> None:
    entitlement = await repository.get_entitlement_by_scope_model(
        tenant_id=tenant_id,
        scope_type=scope_type,
        organization_unit_id=organization_unit_id,
        llm_config_id=llm_config_id,
    )
    if entitlement is None or entitlement.status != ACTIVE_STATUS:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "该范围未分配可用模型，不能绑定。",
        )


async def ensure_parent_entitlement(
    *,
    tenant_id: str,
    scope_type: str,
    organization_unit_id: str,
    llm_config_id: str,
    repository: LLMAdminRepository,
    org_repository: ZhizhiLLMOrganizationDirectory,
) -> None:
    parent = await parent_entitlement_scope(
        scope_type=scope_type,
        organization_unit_id=organization_unit_id,
        org_repository=org_repository,
    )
    if parent is None:
        return
    entitlement = await repository.get_entitlement_by_scope_model(
        tenant_id=tenant_id,
        scope_type=parent[0],
        organization_unit_id=parent[1],
        llm_config_id=llm_config_id,
    )
    if entitlement is None or entitlement.status != ACTIVE_STATUS:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "上级范围未分配该模型，不能向下分配。",
        )


async def ensure_entitlement_not_in_use(
    entitlement: ManagedLLMEntitlement,
    repository: LLMAdminRepository,
    org_repository: ZhizhiLLMOrganizationDirectory,
) -> None:
    if await repository.binding_exists(
        llm_config_id=entitlement.llm_config_id,
        tenant_id=entitlement.tenant_id,
        scope_type=entitlement.scope_type,
        organization_unit_id=entitlement.organization_unit_id,
    ):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "该模型分配仍存在绑定关系，不能停用或删除。",
        )
    child_scope_type, child_organization_unit_ids = await _child_entitlement_filter(
        entitlement.scope_type,
        entitlement.organization_unit_id,
        org_repository,
    )
    if child_scope_type is not None and await repository.entitlement_exists(
        llm_config_id=entitlement.llm_config_id,
        tenant_id=entitlement.tenant_id,
        scope_type=child_scope_type,
        organization_unit_ids=child_organization_unit_ids,
        exclude_id=entitlement.id,
    ):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "该模型分配仍存在下级分配，不能停用或删除。",
        )


async def _child_entitlement_filter(
    scope_type: str,
    organization_unit_id: str,
    org_repository: ZhizhiLLMOrganizationDirectory,
) -> tuple[str | None, tuple[str, ...] | None]:
    if scope_type == BINDING_SCOPE_TENANT:
        return BINDING_SCOPE_ORGANIZATION_UNIT, None
    if scope_type == BINDING_SCOPE_ORGANIZATION_UNIT:
        descendants = await org_repository.descendant_ids((organization_unit_id,))
        return BINDING_SCOPE_ORGANIZATION_UNIT, tuple(descendants)
    return None, None


async def parent_entitlement_scope(
    *,
    scope_type: str,
    organization_unit_id: str,
    org_repository: ZhizhiLLMOrganizationDirectory,
) -> tuple[str, str] | None:
    if scope_type == BINDING_SCOPE_TENANT:
        return None
    unit = await org_repository.get_organization_unit(organization_unit_id)
    if unit is None:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT, "Organization unit does not exist."
        )
    if not unit.parent_id:
        return (BINDING_SCOPE_TENANT, "")
    return (BINDING_SCOPE_ORGANIZATION_UNIT, unit.parent_id)


async def validate_binding_target(
    *,
    tenant_id: str,
    scope_type: str,
    organization_unit_id: str,
    org_repository: ZhizhiLLMOrganizationDirectory,
) -> str:
    tenant = await org_repository.get_tenant(tenant_id)
    if tenant is None or tenant.status != ACTIVE_STATUS:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "租户不存在或未启用。")
    if scope_type == BINDING_SCOPE_TENANT:
        if organization_unit_id:
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "租户级绑定不能带地域。")
        return ""
    if scope_type != BINDING_SCOPE_ORGANIZATION_UNIT or not organization_unit_id:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Organization-unit binding requires organization_unit_id.",
        )
    unit = await org_repository.get_organization_unit(organization_unit_id)
    if unit is None or unit.status != ACTIVE_STATUS or unit.tenant_id != tenant_id:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Organization unit does not exist, is inactive, or belongs to another tenant.",
        )
    return organization_unit_id


async def binding_admin_scope(
    *,
    tenant_id: str,
    scope_type: str,
    organization_unit_id: str,
    org_repository: ZhizhiLLMOrganizationDirectory,
) -> AdminScopeRef:
    if scope_type == BINDING_SCOPE_TENANT:
        return AdminScopeRef(
            scope_type=AdminScopeType.TENANT,
            scope_tenant_id=tenant_id,
        )
    path = await org_repository.get_organization_path(tenant_id, organization_unit_id)
    return AdminScopeRef(
        scope_type=AdminScopeType.ORGANIZATION_UNIT,
        scope_tenant_id=tenant_id,
        scope_organization_unit_id=organization_unit_id,
        scope_organization_path=tuple(
            OrganizationUnitRef(
                id=unit.id,
                external_key=unit.external_key,
                name=unit.name,
                unit_type=unit.unit_type,
                storage_key=unit.storage_key,
            )
            for unit in path
        ),
    )


def require_scoped_permission(
    session_user: AdminSessionUser,
    permission_code: str,
    scope: AdminScopeRef,
) -> None:
    if not has_admin_scoped_permission(session_user, permission_code, scope):
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            f"Missing scoped permission: {permission_code}",
        )


def require_parent_entitlement_permission(
    session_user: AdminSessionUser,
    permission_code: str,
    scope: AdminScopeRef,
) -> None:
    if not has_admin_parent_scoped_permission(session_user, permission_code, scope):
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            "只有上级管理员可以管理可用模型。",
        )


def validate_binding_scope(scope_type: str) -> str:
    if scope_type not in BINDING_SCOPES:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Binding scope must be tenant or organization_unit.",
        )
    return scope_type


def public_config(
    config: ManagedLLMConfig,
    cipher: LLMCredentialCipher,
) -> dict[str, object]:
    payload = config.model_dump(mode="json", exclude={"credentials_ciphertext"})
    payload["has_credentials"] = config.credential_status == CONFIGURED_CREDENTIAL_STATUS
    payload["credential_fields"] = credential_fields(config, cipher)
    return payload


def scoped_config(
    config: ManagedLLMConfig,
    cipher: LLMCredentialCipher,
) -> dict[str, object]:
    payload = public_config(config, cipher)
    payload["endpoint_url"] = ""
    payload["provider_config"] = {"context_window": context_window(config.provider_config)}
    payload["last_test_message"] = ""
    return payload


def public_binding(binding: ManagedLLMBinding) -> dict[str, object]:
    return binding.model_dump(mode="json")


def public_entitlement(entitlement: ManagedLLMEntitlement) -> dict[str, object]:
    return entitlement.model_dump(mode="json")


def stable_code(value: str) -> str:
    return value.strip()


def _bounded_number(key: str, value: Any, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, f"{key} 必须是数字。") from exc
    if number < minimum or number > maximum:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            f"{key} 必须在 {minimum:g} 到 {maximum:g} 之间。",
        )
    return number


def _positive_int(key: str, value: Any, *, allow_zero: bool = False) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, f"{key} 必须是整数。") from exc
    minimum = 0 if allow_zero else 1
    if number < minimum:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            f"{key} 必须大于等于 {minimum}。",
        )
    return number


def _redact_secret_values(message: str, secret_values: tuple[str, ...]) -> str:
    redacted = message
    for secret in secret_values:
        redacted = redacted.replace(secret, "***")
    return redacted


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else "" if value is None else str(value)


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_string_values(value: Any) -> dict[str, str]:
    return {
        str(key): str(item)
        for key, item in _dict_value(value).items()
        if item is not None and str(item) != ""
    }


def _role_reflect(provider_config: dict[str, Any]) -> dict[str, str]:
    value = provider_config.get("role_reflect")
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except JSONDecodeError:
            parsed = {}
        value = parsed
    mapping = _dict_value(value)
    return {
        "system": _string_value(mapping.get("system") or "system"),
        "assistant": _string_value(mapping.get("assistant") or "assistant"),
        "user": _string_value(mapping.get("user") or "user"),
    }


def _unicom_req_key(provider_config: dict[str, Any]) -> str:
    return _string_value(provider_config.get("req_key") or provider_config.get("app_req_key"))


def _credential_api_key(credentials: dict[str, Any]) -> str:
    return _string_value(credentials.get("api_key"))


def _nlpt_authorization(credentials: dict[str, Any]) -> str:
    return _string_value(
        credentials.get("nlpt_authorization") or credentials.get("nlpt-Authorization")
    )
