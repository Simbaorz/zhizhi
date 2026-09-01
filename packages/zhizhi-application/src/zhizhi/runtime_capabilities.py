"""Resolve Zhizhi configuration under a shared-only workspace policy."""

from __future__ import annotations

from typing import Protocol

from gewu_agent_runtime.builtins import SceneCatalog, SkillCatalog
from gewu_agent_runtime.prompts import WorkspacePromptContext
from gewu_agent_runtime.tools import PersistencePolicy, ToolRuntimeBindings
from zhizhi.capabilities import ReadOnlyWorkspaceBackends
from zhizhi.provider import ResolvedTurnCapabilities
from zhizhi.scope import AgentScope
from zhizhi_platform.data_source.tool import data_source_tool
from zhizhi_platform.iam import AccessScope, ScopeType
from zhizhi_platform.prompt import build_zhizhi_system_prompt
from zhizhi_platform.runtime_contracts import (
    ZhizhiDataSourceResolver,
    ZhizhiModelNotConfiguredError,
    ZhizhiTurnModelResolver,
)
from zhizhi_platform.workspace import ScopedBackendFactory


class AgentCatalogResolver(Protocol):
    async def resolve(
        self,
        scope: AgentScope,
    ) -> tuple[SkillCatalog, SceneCatalog]: ...


class ZhizhiCapabilityResolver:
    """Adapt managed configuration to an Zhizhi turn."""

    def __init__(
        self,
        *,
        models: ZhizhiTurnModelResolver,
        data_source: ZhizhiDataSourceResolver,
        catalogs: AgentCatalogResolver,
        workspace_backends: ScopedBackendFactory,
        tool_runtime: ToolRuntimeBindings | None = None,
        max_iterations: int = 50,
        ask_timeout_seconds: int = 300,
        data_source_max_result_bytes: int = 256 * 1024,
    ) -> None:
        self._models = models
        self._data_source = data_source
        self._catalogs = catalogs
        self._workspace_backends = workspace_backends
        self._tool_runtime = tool_runtime or ToolRuntimeBindings()
        self._max_iterations = max_iterations
        self._ask_timeout_seconds = ask_timeout_seconds
        self._data_source_max_result_bytes = data_source_max_result_bytes

    async def resolve(self, scope: AgentScope) -> ResolvedTurnCapabilities:
        access = agent_access_scope(scope)
        resolved_model = await self._models.resolve(access)
        if resolved_model is None:
            raise ZhizhiModelNotConfiguredError()
        skill_catalog, scene_catalog = await self._catalogs.resolve(scope)
        data_binding = await self._data_source.resolve(access)
        data_tool = None
        if data_binding is not None:
            data_tool = data_source_tool(
                data_binding.capability,
                database_key=data_binding.database_key,
                row_limit=data_binding.row_limit,
                max_result_bytes=self._data_source_max_result_bytes,
            ).model_copy(update={"persistence_policy": PersistencePolicy.PROTECTED})
        shared = access.shared_ancestor_scopes()
        return ResolvedTurnCapabilities(
            model=resolved_model.model,
            prompt=build_zhizhi_system_prompt(
                workspace=_workspace_prompt(len(access.organization_path))
            ),
            workspace_backends=ReadOnlyWorkspaceBackends(
                tenant=self._workspace_backends(shared[0]),
                organization=tuple(self._workspace_backends(item) for item in shared[1:]),
            ),
            data_source_tool=data_tool,
            skill_catalog=skill_catalog,
            scene_catalog=scene_catalog,
            tool_runtime=self._tool_runtime,
            max_iterations=self._max_iterations,
            ask_timeout_seconds=self._ask_timeout_seconds,
        )

    async def supports_vision(self, scope: AgentScope) -> bool:
        """Read image support from the same effective model used by the turn."""

        resolved_model = await self._models.resolve(agent_access_scope(scope))
        if resolved_model is None:
            raise ZhizhiModelNotConfiguredError()
        return resolved_model.model.support_vision


def agent_access_scope(scope: AgentScope) -> AccessScope:
    """Build a read-only tenant and active organization scope."""

    return AccessScope(
        tenant_id=scope.tenant_id,
        tenant_storage_key=scope.tenant_storage_key,
        scope_type=(ScopeType.ORGANIZATION_UNIT if scope.organization_path else ScopeType.TENANT),
        organization_path=scope.organization_path,
        principal_id=scope.principal_id,
        principal_type=scope.principal_type,
    )


def _workspace_prompt(organization_depth: int) -> WorkspacePromptContext:
    organization_roots = tuple(
        f"/workspace/organization-{index}" for index in range(1, organization_depth + 1)
    )
    readable_roots = ("/workspace/tenant", *organization_roots)
    return WorkspacePromptContext(
        writable_roots=(),
        readable_roots=readable_roots,
        relative_path_root=readable_roots[-1],
        relative_path_description=(
            "Relative paths resolve under the active organization workspace."
        ),
        rules=(
            "All workspace paths are read-only.",
            "Use only the tenant and organization roots listed above.",
        ),
    )
