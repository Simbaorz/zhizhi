"""Admin configuration and strict-parent resource delegation for SQL sources."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from gewu_core import JsonSecretCipher
from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.data_source.domain import DataSourceConfig, SourceBinding, SourceEntitlement
from zhizhi_platform.data_source.ports import DataSourceOrganizationDirectory
from zhizhi_platform.data_source.repository import DataSourceRepository
from zhizhi_platform.iam import (
    AdminScopeRef,
    AdminScopeType,
    AdminSessionUser,
    OrganizationUnitRef,
    ensure_admin_scoped_permission,
    ensure_super_admin,
    has_admin_parent_scoped_permission,
    has_admin_scoped_permission,
)


class DataSourceAdminService:
    def __init__(
        self,
        repository: DataSourceRepository,
        organizations: DataSourceOrganizationDirectory,
        key: str,
    ) -> None:
        self.repository = repository
        self.organizations = organizations
        self.key = key

    async def scope(self, tenant_id: str, unit_id: str = "") -> AdminScopeRef:
        tenant = await self.organizations.get_tenant(tenant_id)
        if tenant is None or tenant.status != "active":
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "租户不存在或未启用。")
        path = await self.organizations.get_organization_path(tenant_id, unit_id) if unit_id else ()
        if unit_id and (
            not path or any(unit.status != "active" or unit.tenant_id != tenant_id for unit in path)
        ):
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT, "组织不存在或不属于当前租户。"
            )
        return AdminScopeRef(
            scope_type=AdminScopeType.ORGANIZATION_UNIT if unit_id else AdminScopeType.TENANT,
            scope_tenant_id=tenant_id,
            scope_organization_unit_id=unit_id,
            scope_organization_path=tuple(
                OrganizationUnitRef(
                    id=unit.id,
                    external_key=unit.external_key,
                    name=unit.name,
                    storage_key=unit.storage_key,
                )
                for unit in path
            ),
        )

    async def list_sources(
        self,
        user: AdminSessionUser,
        *,
        tenant_id: str = "",
        unit_id: str = "",
        page: int = 1,
        page_size: int = 50,
        search: str = "",
    ) -> dict[str, object]:
        source_ids = None
        if tenant_id:
            scope = await self.scope(tenant_id, unit_id)
            ensure_admin_scoped_permission(user, "data_sources.view", scope)
            source_ids = tuple(
                item.source_id
                for item in await self.repository.list_entitlements(tenant_id, unit_id)
            )
        else:
            ensure_super_admin(user)
        sources, total = await self.repository.list_sources(
            page=page, page_size=page_size, search=search, source_ids=source_ids
        )
        return {
            "items": [source.public(detailed=user.is_super) for source in sources],
            "pagination": {"page": page, "page_size": page_size, "total": total},
        }

    async def save_source(
        self,
        user: AdminSessionUser,
        values: dict[str, Any],
        password: str | None,
        *,
        source_id: str = "",
    ) -> dict[str, object]:
        ensure_super_admin(user)
        old = await self.require_source(source_id) if source_id else None
        expected_revision = values.pop("revision", None)
        if old and expected_revision is not None and expected_revision != old.revision:
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT, "数据源配置已更新，请刷新后再保存。"
            )
        ciphertext = old.credentials_ciphertext if old else ""
        if password is not None:
            if not password or not self.key.strip():
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT,
                    "数据库密码和 storage_encryption.key 必须配置。",
                )
            ciphertext = JsonSecretCipher(self.key).encrypt({"password": password})
        if not ciphertext:
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "必须配置数据库密码。")
        values = {**values, "id": source_id, "credentials_ciphertext": ciphertext}
        if old:
            if values["source_key"] != old.source_key:
                raise ApplicationError(
                    ApplicationErrorKind.INVALID_INPUT, "资源编号创建后不可更改。"
                )
            connection_fields = {
                "driver",
                "host",
                "port",
                "database",
                "username",
                "credentials_ciphertext",
                "tls",
                "pool_size",
                "pool_timeout_seconds",
                "connect_timeout_seconds",
            }
            changed = any(
                values.get(field, getattr(old, field)) != getattr(old, field)
                for field in connection_fields
            )
            values["connection_revision"] = old.connection_revision + int(changed)
            values["last_test_status"] = "untested" if changed else old.last_test_status
        values["revision"] = old.revision if old else 1
        try:
            source = DataSourceConfig.model_validate(values)
        except ValidationError as exc:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "数据源配置无效，请检查编号、标签、服务地址及连接限制。",
            ) from exc
        if old and source.tag != old.tag:
            for binding in await self.repository.list_bindings():
                if source.id in binding.source_ids:
                    others = [
                        await self.require_source(item)
                        for item in binding.source_ids
                        if item != source.id
                    ]
                    if any(item.tag == source.tag for item in others):
                        raise ApplicationError(
                            ApplicationErrorKind.CONFLICT, "标签与现有绑定中的其他数据源冲突。"
                        )
        source = await self.repository.save_source(source)
        return source.public(detailed=True)

    async def delete_source(self, user: AdminSessionUser, source_id: str) -> None:
        ensure_super_admin(user)
        await self.require_source(source_id)
        if await self.repository.allocated(source_id) or any(
            source_id in binding.source_ids for binding in await self.repository.list_bindings()
        ):
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT, "请先解除资源绑定和授权，再删除数据源。"
            )
        await self.repository.delete_source(source_id)

    async def require_source(self, source_id: str) -> DataSourceConfig:
        source = await self.repository.get_source(source_id)
        if source is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "数据源不存在。")
        return source

    async def parent_id(self, unit_id: str) -> str | None:
        if not unit_id:
            return None
        unit = await self.organizations.get_organization_unit(unit_id)
        if unit is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "组织不存在。")
        return unit.parent_id or ""

    async def list_resources(
        self, user: AdminSessionUser, tenant_id: str, unit_id: str, *, kind: str
    ) -> dict[str, object]:
        scope = await self.scope(tenant_id, unit_id)
        ensure_admin_scoped_permission(user, "data_sources.view", scope)
        if kind == "bindings":
            items = [
                binding.model_dump(mode="json")
                for binding in await self.repository.list_bindings(tenant_id)
                if binding.organization_unit_id == unit_id
            ]
            for payload in items:
                binding = SourceBinding.model_validate(payload)
                payload["sources"] = [
                    (await self.require_source(source_id)).public(detailed=False)
                    for source_id in binding.source_ids
                ]
        else:
            items = [
                grant.model_dump(mode="json")
                for grant in await self.repository.list_entitlements(tenant_id, unit_id)
            ]
        return {"items": items}

    async def assignable(
        self,
        user: AdminSessionUser,
        tenant_id: str,
        unit_id: str,
        page: int,
        page_size: int,
        search: str,
    ) -> dict[str, object]:
        scope = await self.scope(tenant_id, unit_id)
        if not has_admin_parent_scoped_permission(user, "data_sources.entitlements.edit", scope):
            raise ApplicationError(
                ApplicationErrorKind.FORBIDDEN, "只有上级管理员可以分配可用数据源。"
            )
        parent = await self.parent_id(unit_id)
        source_ids = (
            None
            if parent is None
            else tuple(
                item.source_id
                for item in await self.repository.list_entitlements(tenant_id, parent)
            )
        )
        sources, total = await self.repository.list_sources(
            page=page, page_size=page_size, search=search, source_ids=source_ids
        )
        return {
            "items": [source.public(detailed=False) for source in sources],
            "pagination": {"page": page, "page_size": page_size, "total": total},
        }

    async def grant(self, user: AdminSessionUser, grant: SourceEntitlement) -> SourceEntitlement:
        scope = await self.scope(grant.tenant_id, grant.organization_unit_id)
        if not has_admin_parent_scoped_permission(user, "data_sources.entitlements.edit", scope):
            raise ApplicationError(
                ApplicationErrorKind.FORBIDDEN, "只有上级管理员可以分配可用数据源。"
            )
        source = await self.require_source(grant.source_id)
        if source.status != "active":
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, "不能分配已停用的数据源。")
        parent = await self.parent_id(grant.organization_unit_id)
        if (
            parent is not None
            and await self.repository.get_entitlement(grant.tenant_id, parent, source.id) is None
        ):
            raise ApplicationError(
                ApplicationErrorKind.FORBIDDEN, "上级范围没有该数据源，不能向下分配。"
            )
        existing = await self.repository.get_entitlement(
            grant.tenant_id, grant.organization_unit_id, source.id
        )
        return existing or await self.repository.save_entitlement(grant)

    async def revoke(
        self, user: AdminSessionUser, tenant_id: str, unit_id: str, source_id: str
    ) -> None:
        scope = await self.scope(tenant_id, unit_id)
        if not has_admin_parent_scoped_permission(user, "data_sources.entitlements.edit", scope):
            raise ApplicationError(
                ApplicationErrorKind.FORBIDDEN, "只有上级管理员可以撤销可用资源。"
            )
        grant = await self.repository.get_entitlement(tenant_id, unit_id, source_id)
        if grant is None:
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "资源授权不存在。")
        descendants = (
            set(await self.organizations.descendant_ids((unit_id,)))
            if unit_id
            else {
                item.organization_unit_id
                for item in await self.repository.list_entitlements(tenant_id)
            }
        )
        affected = descendants | {unit_id}
        if any(
            source_id in binding.source_ids and binding.organization_unit_id in affected
            for binding in await self.repository.list_bindings(tenant_id)
        ) or any(
            item.source_id == source_id and item.organization_unit_id in affected - {unit_id}
            for item in await self.repository.list_entitlements(tenant_id)
        ):
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT, "该资源仍有绑定或下级授权，请先解除。"
            )
        await self.repository.delete_entitlement(grant.id)

    async def bind(self, user: AdminSessionUser, binding: SourceBinding) -> SourceBinding:
        scope = await self.scope(binding.tenant_id, binding.organization_unit_id)
        ensure_admin_scoped_permission(user, "data_sources.bindings.edit", scope)
        sources = []
        for source_id in binding.source_ids:
            source = await self.require_source(source_id)
            if (
                source.status != "active"
                or await self.repository.get_entitlement(
                    binding.tenant_id, binding.organization_unit_id, source_id
                )
                is None
            ):
                raise ApplicationError(
                    ApplicationErrorKind.FORBIDDEN, "绑定的数据源必须属于当前可用池且已启用。"
                )
            sources.append(source)
        if len({source.tag for source in sources}) != len(sources):
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT, "同一绑定集合中的数据源标签不能重复。"
            )
        return await self.repository.save_binding(binding)

    async def unbind(self, user: AdminSessionUser, tenant_id: str, unit_id: str) -> None:
        scope = await self.scope(tenant_id, unit_id)
        ensure_admin_scoped_permission(user, "data_sources.bindings.edit", scope)
        binding = next(
            (
                item
                for item in await self.repository.list_bindings(tenant_id)
                if item.organization_unit_id == unit_id
            ),
            None,
        )
        if binding:
            await self.repository.delete_binding(binding.id)

    async def visible_binding(self, user: AdminSessionUser, tenant_id: str, unit_id: str) -> bool:
        return has_admin_scoped_permission(
            user, "data_sources.view", await self.scope(tenant_id, unit_id)
        )
