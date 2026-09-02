"""致知 composition-root query for references to IAM organization nodes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from zhizhi.assets import SharedAssetModel

from zhizhi_platform.data_source.adapters.mysql.models import (
    DataSourceSourceBindingModel,
    DataSourceSourceEntitlementModel,
)
from zhizhi_platform.git.adapters.mysql.models import (
    GitEntitlementModel,
    WorkspaceSceneGitConfigModel,
)
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminTenantMemberModel,
    AdminTenantScopeModel,
    OrganizationUnitModel,
)
from zhizhi_platform.llm.adapters.mysql.models import (
    LLMBindingModel,
    LLMEntitlementModel,
)
from zhizhi_platform.workspace.adapters.mysql.models import (
    BackgroundJobModel,
)

SessionFactory = Callable[[], AsyncSession]
DELETED_STATUS = "deleted"


class MysqlOrganizationReferenceQuery:
    """Count references owned by 致知 packages without leaking their ORM into IAM."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    async def count_references(
        self,
        *,
        tenant_id: str = "",
        organization_unit_id: str = "",
    ) -> dict[str, int]:
        """Return non-zero reference counts for one 致知 organization node."""

        count_queries: list[tuple[str, Any]] = []

        def add_count(name_: str, model_: type[Any], *conditions: Any) -> None:
            count_queries.append(
                (
                    name_,
                    select(func.count()).select_from(model_).where(*conditions).scalar_subquery(),
                )
            )

        if tenant_id and not organization_unit_id:
            tenant_counts = (
                (
                    "admin_members",
                    AdminTenantMemberModel,
                    AdminTenantMemberModel.tenant_id == tenant_id,
                ),
                (
                    "llm_entitlements",
                    LLMEntitlementModel,
                    LLMEntitlementModel.tenant_id == tenant_id,
                ),
                ("llm_bindings", LLMBindingModel, LLMBindingModel.tenant_id == tenant_id),
                (
                    "data_source_entitlements",
                    DataSourceSourceEntitlementModel,
                    DataSourceSourceEntitlementModel.tenant_id == tenant_id,
                ),
                (
                    "data_source_bindings",
                    DataSourceSourceBindingModel,
                    DataSourceSourceBindingModel.tenant_id == tenant_id,
                ),
                (
                    "git_entitlements",
                    GitEntitlementModel,
                    GitEntitlementModel.tenant_id == tenant_id,
                ),
                (
                    "scene_git_configs",
                    WorkspaceSceneGitConfigModel,
                    WorkspaceSceneGitConfigModel.tenant_id == tenant_id,
                ),
                (
                    "background_jobs",
                    BackgroundJobModel,
                    BackgroundJobModel.payload["tenant_id"].as_string() == tenant_id,
                ),
            )
            for name, model, condition in tenant_counts:
                add_count(name, model, condition)
            add_count(
                "skill_assets",
                SharedAssetModel,
                SharedAssetModel.kind == "skill",
                SharedAssetModel.tenant_id == tenant_id,
                SharedAssetModel.status != DELETED_STATUS,
            )
            add_count(
                "scene_assets",
                SharedAssetModel,
                SharedAssetModel.kind == "scene",
                SharedAssetModel.tenant_id == tenant_id,
                SharedAssetModel.status != DELETED_STATUS,
            )

        if organization_unit_id:
            llm_entitlement_conditions = [
                LLMEntitlementModel.organization_unit_id == organization_unit_id
            ]
            llm_binding_conditions = [LLMBindingModel.organization_unit_id == organization_unit_id]
            business_entitlement_conditions = [
                DataSourceSourceEntitlementModel.organization_unit_id == organization_unit_id
            ]
            business_binding_conditions = [
                DataSourceSourceBindingModel.organization_unit_id == organization_unit_id
            ]
            if tenant_id:
                llm_entitlement_conditions.append(LLMEntitlementModel.tenant_id == tenant_id)
                llm_binding_conditions.append(LLMBindingModel.tenant_id == tenant_id)
                business_entitlement_conditions.append(
                    DataSourceSourceEntitlementModel.tenant_id == tenant_id
                )
                business_binding_conditions.append(
                    DataSourceSourceBindingModel.tenant_id == tenant_id
                )
            count_queries.append(
                (
                    "admin_scopes",
                    self._admin_scope_count(
                        tenant_id=tenant_id, organization_unit_id=organization_unit_id
                    ),
                )
            )
            add_count("llm_entitlements", LLMEntitlementModel, *llm_entitlement_conditions)
            add_count("llm_bindings", LLMBindingModel, *llm_binding_conditions)
            add_count(
                "data_source_entitlements",
                DataSourceSourceEntitlementModel,
                *business_entitlement_conditions,
            )
            add_count(
                "data_source_bindings",
                DataSourceSourceBindingModel,
                *business_binding_conditions,
            )

        return await self._load_nonzero_counts(count_queries)

    async def count_organization_unit_removal_references(
        self,
        tenant_id: str,
        retained_organization_unit_ids: Sequence[str],
    ) -> dict[str, int]:
        """Count references to active organization units excluded by replacement."""

        removed_organization_unit_ids = select(OrganizationUnitModel.id).where(
            OrganizationUnitModel.tenant_id == tenant_id,
            OrganizationUnitModel.status == "active",
        )
        retained_ids = tuple(dict.fromkeys(retained_organization_unit_ids))
        if retained_ids:
            removed_organization_unit_ids = removed_organization_unit_ids.where(
                OrganizationUnitModel.id.not_in(retained_ids)
            )

        def count(model: type[Any], *conditions: Any) -> Any:
            return select(func.count()).select_from(model).where(*conditions).scalar_subquery()

        count_queries = [
            (
                "admin_scopes",
                self._admin_scope_removal_count(tenant_id, removed_organization_unit_ids),
            ),
            (
                "llm_entitlements",
                count(
                    LLMEntitlementModel,
                    LLMEntitlementModel.tenant_id == tenant_id,
                    LLMEntitlementModel.organization_unit_id.in_(removed_organization_unit_ids),
                ),
            ),
            (
                "llm_bindings",
                count(
                    LLMBindingModel,
                    LLMBindingModel.tenant_id == tenant_id,
                    LLMBindingModel.organization_unit_id.in_(removed_organization_unit_ids),
                ),
            ),
            (
                "data_source_entitlements",
                count(
                    DataSourceSourceEntitlementModel,
                    DataSourceSourceEntitlementModel.tenant_id == tenant_id,
                    DataSourceSourceEntitlementModel.organization_unit_id.in_(
                        removed_organization_unit_ids
                    ),
                ),
            ),
            (
                "data_source_bindings",
                count(
                    DataSourceSourceBindingModel,
                    DataSourceSourceBindingModel.tenant_id == tenant_id,
                    DataSourceSourceBindingModel.organization_unit_id.in_(
                        removed_organization_unit_ids
                    ),
                ),
            ),
        ]
        return await self._load_nonzero_counts(count_queries)

    async def _load_nonzero_counts(
        self,
        count_queries: Sequence[tuple[str, Any]],
    ) -> dict[str, int]:
        if not count_queries:
            return {}
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(
                        *(
                            query.label(f"reference_{index}")
                            for index, (_, query) in enumerate(count_queries)
                        )
                    )
                )
            ).one()
        return {
            name: count
            for (name, _), value in zip(count_queries, row, strict=True)
            if (count := int(value or 0))
        }

    @staticmethod
    def _admin_scope_removal_count(tenant_id: str, removed_organization_unit_ids: Any) -> Any:
        return (
            select(func.count())
            .select_from(AdminTenantScopeModel)
            .join(
                AdminTenantMemberModel,
                AdminTenantMemberModel.id == AdminTenantScopeModel.tenant_member_id,
            )
            .where(
                AdminTenantMemberModel.tenant_id == tenant_id,
                or_(
                    AdminTenantScopeModel.scope_organization_unit_id.in_(
                        removed_organization_unit_ids
                    ),
                ),
            )
            .scalar_subquery()
        )

    @staticmethod
    def _admin_scope_count(
        *,
        tenant_id: str,
        organization_unit_id: str = "",
    ) -> Any:
        statement = (
            select(func.count())
            .select_from(AdminTenantScopeModel)
            .join(
                AdminTenantMemberModel,
                AdminTenantMemberModel.id == AdminTenantScopeModel.tenant_member_id,
            )
        )
        if organization_unit_id:
            statement = statement.where(
                AdminTenantScopeModel.scope_organization_unit_id == organization_unit_id
            )
        if tenant_id:
            statement = statement.where(AdminTenantMemberModel.tenant_id == tenant_id)
        return statement.scalar_subquery()
