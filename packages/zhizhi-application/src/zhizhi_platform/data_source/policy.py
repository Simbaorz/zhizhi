"""Zhizhi Data Source validation, hierarchy, authorization, and projections."""

from __future__ import annotations

from typing import Any

from gewu_core import ApplicationError, ApplicationErrorKind
from zhizhi_platform.data_source.domain import (
    ManagedDataSourceSource,
    ManagedDataSourceSourceBinding,
    ManagedDataSourceSourceEntitlement,
)
from zhizhi_platform.data_source.ports import (
    DataSourceAdminRepository,
    DataSourceCredentialCipher,
    ZhizhiDataSourceOrganizationDirectory,
)
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
    OrganizationUnitRef,
    has_admin_parent_scoped_permission,
    has_admin_scoped_permission,
)
from zhizhi_platform.iam.codes import canonical_stable_code, validate_stable_code

ACTIVE_STATUS = "active"
INACTIVE_STATUS = "inactive"
VALID_STATUSES = {ACTIVE_STATUS, INACTIVE_STATUS}
CONFIGURED_CREDENTIAL_STATUS = "configured"
CREDENTIAL_FIELDS = ("app_key", "app_secret")
BINDING_SCOPE_TENANT = "tenant"
BINDING_SCOPE_ORGANIZATION_UNIT = "organization_unit"
BINDING_SCOPES = {BINDING_SCOPE_TENANT, BINDING_SCOPE_ORGANIZATION_UNIT}


def validate_status(status: str) -> str:
    """Return a supported activation status."""

    if status not in VALID_STATUSES:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "状态必须是 active 或 inactive。",
        )
    return status


def validate_source_config(
    *,
    api_url: str,
    app_id: str,
    default_database_key: str,
    exec_sources_code: str,
    timeout_seconds: int,
    default_max_rows: int,
    hard_max_rows: int,
) -> None:
    """Validate common Data Source source settings."""

    clean_required(api_url, "接口地址不能为空。")
    clean_required(str(app_id), "应用 ID 不能为空。")
    clean_required(default_database_key, "默认数据库 Key 不能为空。")
    clean_required(exec_sources_code, "执行来源编码不能为空。")
    if timeout_seconds < 1 or timeout_seconds > 3600:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "超时时间必须在 1-3600 秒之间。",
        )
    if hard_max_rows < 1:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "硬性最大行数必须大于 0。",
        )
    if default_max_rows < 1 or default_max_rows > hard_max_rows:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "默认行数必须在 1 到硬性最大行数之间。",
        )


def normalize_credentials(credentials: dict[str, Any]) -> dict[str, str]:
    """Return the canonical credential payload."""

    return {
        field_name: str(credentials.get(field_name) or "").strip()
        for field_name in CREDENTIAL_FIELDS
    }


def validate_credentials(credentials: dict[str, str]) -> None:
    """Require every supported Data Source credential field."""

    missing = [field_name for field_name in CREDENTIAL_FIELDS if not credentials.get(field_name)]
    if missing:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            f"数据源密钥缺少字段：{', '.join(missing)}。",
        )


def decrypt_credentials(
    source: ManagedDataSourceSource,
    cipher: DataSourceCredentialCipher,
) -> dict[str, Any]:
    """Decrypt a stored Data Source source credential payload."""

    try:
        return cipher.decrypt(source.credentials_ciphertext)
    except Exception as exc:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "数据源密钥无法解密，请重新配置。",
        ) from exc


def credential_fields(
    source: ManagedDataSourceSource,
    cipher: DataSourceCredentialCipher,
) -> list[str]:
    """Return configured credential names without exposing values."""

    if source.credential_status != CONFIGURED_CREDENTIAL_STATUS:
        return []
    try:
        credentials = decrypt_credentials(source, cipher)
    except ApplicationError:
        return []
    return [field_name for field_name in CREDENTIAL_FIELDS if credentials.get(field_name)]


def stable_code(value: str, label: str) -> str:
    """Normalize one stable Zhizhi organization or resource code."""

    raw_value = value.strip()
    if len(raw_value) == 32 and all(ch in "0123456789abcdef" for ch in raw_value):
        return raw_value
    try:
        return canonical_stable_code(validate_stable_code(value, label))
    except ValueError as exc:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, str(exc)) from exc


def clean_required(value: str, message: str) -> str:
    """Normalize one required text value."""

    normalized = str(value).strip()
    if not normalized:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, message)
    return normalized


def public_source(
    source: ManagedDataSourceSource,
    cipher: DataSourceCredentialCipher,
) -> dict[str, object]:
    """Return one source without credential values."""

    payload = source.model_dump(mode="json", exclude={"credentials_ciphertext"})
    payload["has_credentials"] = source.credential_status == CONFIGURED_CREDENTIAL_STATUS
    payload["credential_fields"] = credential_fields(source, cipher)
    return payload


def public_binding(binding: ManagedDataSourceSourceBinding) -> dict[str, object]:
    """Return one exact organization-scope binding response."""

    return binding.model_dump(mode="json")


def public_entitlement(
    entitlement: ManagedDataSourceSourceEntitlement,
) -> dict[str, object]:
    """Return one source entitlement response."""

    return entitlement.model_dump(mode="json")


async def require_source(
    source_id: str,
    repository: DataSourceAdminRepository,
) -> ManagedDataSourceSource:
    """Load one source or report the exact Zhizhi application error."""

    source = await repository.get_source(source_id)
    if source is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "数据源不存在。")
    return source


async def require_binding(
    binding_id: str,
    repository: DataSourceAdminRepository,
) -> ManagedDataSourceSourceBinding:
    """Load one binding or report the exact Zhizhi application error."""

    binding = await repository.get_binding(binding_id)
    if binding is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "数据源绑定不存在。")
    return binding


async def require_entitlement(
    entitlement_id: str,
    repository: DataSourceAdminRepository,
) -> ManagedDataSourceSourceEntitlement:
    """Load one entitlement or report the exact Zhizhi application error."""

    entitlement = await repository.get_entitlement(entitlement_id)
    if entitlement is None:
        raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "数据源可用池条目不存在。")
    return entitlement


async def validate_binding_source(
    source_id: str,
    binding_status: str,
    repository: DataSourceAdminRepository,
) -> ManagedDataSourceSource:
    """Ensure an enabled allocation references a usable source."""

    source = await require_source(source_id, repository)
    if binding_status == ACTIVE_STATUS:
        if source.status != ACTIVE_STATUS:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "启用绑定必须选择 active 数据源。",
            )
        if source.credential_status != CONFIGURED_CREDENTIAL_STATUS:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "启用绑定的数据源必须已配置密钥。",
            )
    return source


async def ensure_no_active_allocations(
    source_id: str,
    repository: DataSourceAdminRepository,
) -> None:
    """Reject source deactivation while active allocations reference it."""

    if await repository.binding_exists(data_source_id=source_id, status=ACTIVE_STATUS):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "数据源仍存在启用绑定，不能停用。",
        )
    if await repository.entitlement_exists(data_source_id=source_id, status=ACTIVE_STATUS):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "数据源仍存在启用可用池分配，不能停用。",
        )


async def ensure_no_allocations(
    source_id: str,
    repository: DataSourceAdminRepository,
) -> None:
    """Reject source deletion while any allocation references it."""

    if await repository.binding_exists(data_source_id=source_id):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "数据源仍存在绑定关系，不能删除，请先解除数据源绑定。",
        )
    if await repository.entitlement_exists(data_source_id=source_id):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "数据源仍存在可用池分配，不能删除，请先解除数据源分配。",
        )


async def ensure_active_entitlement(
    *,
    tenant_id: str,
    scope_type: str,
    organization_unit_id: str,
    data_source_id: str,
    repository: DataSourceAdminRepository,
) -> None:
    """Ensure the exact binding scope has an active source allocation."""

    entitlement = await repository.get_entitlement_by_scope_source(
        tenant_id=tenant_id,
        scope_type=scope_type,
        organization_unit_id=organization_unit_id,
        data_source_id=data_source_id,
    )
    if entitlement is None or entitlement.status != ACTIVE_STATUS:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "该范围未分配可用数据源，不能绑定。",
        )


async def ensure_parent_entitlement(
    *,
    tenant_id: str,
    scope_type: str,
    organization_unit_id: str,
    data_source_id: str,
    repository: DataSourceAdminRepository,
    org_repository: ZhizhiDataSourceOrganizationDirectory,
) -> None:
    """Require an active parent allocation before allocating downward."""

    parent = await parent_entitlement_scope(
        scope_type=scope_type,
        organization_unit_id=organization_unit_id,
        org_repository=org_repository,
    )
    if parent is None:
        return
    entitlement = await repository.get_entitlement_by_scope_source(
        tenant_id=tenant_id,
        scope_type=parent[0],
        organization_unit_id=parent[1],
        data_source_id=data_source_id,
    )
    if entitlement is None or entitlement.status != ACTIVE_STATUS:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "上级范围未分配该数据源，不能向下分配。",
        )


async def ensure_entitlement_not_in_use(
    entitlement: ManagedDataSourceSourceEntitlement,
    repository: DataSourceAdminRepository,
    org_repository: ZhizhiDataSourceOrganizationDirectory,
) -> None:
    """Reject removal of an entitlement used by bindings or children."""

    if await repository.binding_exists(
        data_source_id=entitlement.data_source_id,
        tenant_id=entitlement.tenant_id,
        scope_type=entitlement.scope_type,
        organization_unit_id=entitlement.organization_unit_id,
    ):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "该数据源分配仍存在绑定关系，不能停用或删除。",
        )
    child_scope_type, child_organization_unit_ids = await _child_entitlement_filter(
        entitlement.scope_type,
        entitlement.organization_unit_id,
        org_repository,
    )
    if child_scope_type is not None and await repository.entitlement_exists(
        data_source_id=entitlement.data_source_id,
        tenant_id=entitlement.tenant_id,
        scope_type=child_scope_type,
        organization_unit_ids=child_organization_unit_ids,
        exclude_id=entitlement.id,
    ):
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "该数据源分配仍存在下级分配，不能停用或删除。",
        )


async def _child_entitlement_filter(
    scope_type: str,
    organization_unit_id: str,
    org_repository: ZhizhiDataSourceOrganizationDirectory,
) -> tuple[str | None, tuple[str, ...] | None]:
    if scope_type == BINDING_SCOPE_TENANT:
        return BINDING_SCOPE_ORGANIZATION_UNIT, None
    if scope_type == BINDING_SCOPE_ORGANIZATION_UNIT:
        return (
            BINDING_SCOPE_ORGANIZATION_UNIT,
            tuple(await org_repository.descendant_ids((organization_unit_id,))),
        )
    return None, None


async def parent_entitlement_scope(
    *,
    scope_type: str,
    organization_unit_id: str,
    org_repository: ZhizhiDataSourceOrganizationDirectory,
) -> tuple[str, str] | None:
    """Return the direct parent scope for one source allocation."""

    if scope_type == BINDING_SCOPE_TENANT:
        return None
    unit = await org_repository.get_organization_unit(organization_unit_id)
    if unit is None:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT, "Organization unit does not exist."
        )
    if not unit.parent_id:
        return BINDING_SCOPE_TENANT, ""
    return BINDING_SCOPE_ORGANIZATION_UNIT, unit.parent_id


async def validate_binding_target(
    *,
    tenant_id: str,
    scope_type: str,
    organization_unit_id: str,
    org_repository: ZhizhiDataSourceOrganizationDirectory,
) -> str:
    """Validate a tenant or organization-unit allocation target."""

    tenant = await org_repository.get_tenant(tenant_id)
    if tenant is None or tenant.status != ACTIVE_STATUS:
        raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "租户不存在或未启用。")
    if scope_type == BINDING_SCOPE_TENANT:
        if organization_unit_id:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "租户级绑定不能带地域。",
            )
        return ""
    if scope_type != BINDING_SCOPE_ORGANIZATION_UNIT or not organization_unit_id:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Organization-unit scope requires organization_unit_id.",
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
    org_repository: ZhizhiDataSourceOrganizationDirectory,
) -> AdminScopeRef:
    """Return the admin authorization scope for one entitlement."""

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
    """Require a permission granted at the target scope."""

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
    """Require a permission granted by a strict parent scope."""

    if not has_admin_parent_scoped_permission(session_user, permission_code, scope):
        raise ApplicationError(
            ApplicationErrorKind.FORBIDDEN,
            "只有上级管理员可以管理可用数据源。",
        )


def validate_binding_scope(scope_type: str) -> str:
    """Return a supported source allocation scope."""

    if scope_type not in BINDING_SCOPES:
        raise ApplicationError(
            ApplicationErrorKind.INVALID_INPUT,
            "Binding scope must be tenant or organization_unit.",
        )
    return scope_type
