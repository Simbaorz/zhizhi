"""Scope-filtered Slash candidates for the embedded workbench."""

from zhizhi import (
    AgentContext,
    MysqlSharedAssetRepository,
    SlashCandidate,
)
from zhizhi.scope import AgentScope, AgentScopeResolver


class MysqlSlashCatalog:
    """List enabled shared assets while excluding team and personal rows."""

    def __init__(
        self,
        *,
        scopes: AgentScopeResolver,
        assets: MysqlSharedAssetRepository,
    ) -> None:
        self._scopes = scopes
        self._assets = assets

    async def list_skills(self, context: AgentContext) -> tuple[SlashCandidate, ...]:
        scope = await self._require_scope(context)
        return tuple(
            SlashCandidate(
                kind="skill",
                asset_key=asset.asset_key,
                name=asset.name,
                description=asset.description,
            )
            for asset in await self._assets.list_visible(scope, kind="skill")
        )

    async def list_scenes(self, context: AgentContext) -> tuple[SlashCandidate, ...]:
        scope = await self._require_scope(context)
        return tuple(
            SlashCandidate(
                kind="scene",
                asset_key=asset.asset_key,
                name=asset.name,
                description=asset.description,
            )
            for asset in await self._assets.list_visible(scope, kind="scene")
        )

    async def _require_scope(self, context: AgentContext) -> AgentScope:
        scope = await self._scopes.resolve(
            tenant_id=context.tenant_id,
            active_organization_unit_id=context.active_organization_unit_id,
            principal_id=context.principal_id,
            principal_type=context.principal_type,
        )
        if scope is None:
            from gewu_core.errors import ApplicationError, ApplicationErrorKind

            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Tenant or active organization unit is invalid or inactive.",
            )
        return scope
