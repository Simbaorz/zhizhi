"""Resolve 致知 configuration under a shared-only workspace policy."""

from __future__ import annotations

import logging
from typing import Protocol

from gewu_agent_runtime.builtins import SceneCatalog, SkillCatalog
from gewu_agent_runtime.prompts import WorkspacePromptContext
from gewu_agent_runtime.tools import ToolRuntimeBindings
from gewu_core.errors import ApplicationError
from zhizhi.business_data_tool import build_business_data_tool
from zhizhi.capabilities import ReadOnlyWorkspaceBackends
from zhizhi.provider import ResolvedTurnCapabilities
from zhizhi.scope import AgentScope
from zhizhi_platform.data_source.mcp_client import DataMcpClient
from zhizhi_platform.data_source.resolution import DataSourceResolver
from zhizhi_platform.iam import AccessScope, ScopeType
from zhizhi_platform.prompt import (
    ZHIZHI_ASSISTANT_NAME,
    ZHIZHI_DEFAULT_LANGUAGE,
    build_zhizhi_system_prompt,
)
from zhizhi_platform.runtime_contracts import (
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
    """Adapt managed configuration to a 致知 turn."""

    def __init__(
        self,
        *,
        models: ZhizhiTurnModelResolver,
        catalogs: AgentCatalogResolver,
        workspace_backends: ScopedBackendFactory,
        data_sources: DataSourceResolver | None = None,
        data_mcp_client: DataMcpClient | None = None,
        tool_runtime: ToolRuntimeBindings | None = None,
        max_iterations: int = 50,
        ask_timeout_seconds: int = 300,
        assistant_name: str = ZHIZHI_ASSISTANT_NAME,
        language: str = ZHIZHI_DEFAULT_LANGUAGE,
    ) -> None:
        self._models = models
        self._catalogs = catalogs
        self._workspace_backends = workspace_backends
        self._data_sources = data_sources
        self._data_mcp_client = data_mcp_client
        self._tool_runtime = tool_runtime or ToolRuntimeBindings()
        self._max_iterations = max_iterations
        self._ask_timeout_seconds = ask_timeout_seconds
        self._assistant_name = assistant_name
        self._language = language

    async def resolve(self, scope: AgentScope) -> ResolvedTurnCapabilities:
        access = agent_access_scope(scope)
        resolved_model = await self._models.resolve(access)
        if resolved_model is None:
            raise ZhizhiModelNotConfiguredError()
        skill_catalog, scene_catalog = await self._catalogs.resolve(scope)
        shared = access.shared_ancestor_scopes()
        data_tool = None
        if self._data_sources is not None and self._data_mcp_client is not None:
            try:
                selection = await self._data_sources.resolve(access)
            except ApplicationError as exc:
                # Optional SQL access must not disable the caller's authorized Wiki tools.
                logging.getLogger(__name__).warning(
                    "Data-source capability unavailable tenant_id=%s error_kind=%s",
                    scope.tenant_id,
                    exc.kind.value,
                )
                selection = None
            if selection is not None:
                data_tool = build_business_data_tool(
                    selection, self._data_sources, self._data_mcp_client, access
                )
        return ResolvedTurnCapabilities(
            model=resolved_model.model,
            prompt=build_zhizhi_system_prompt(
                workspace=_workspace_prompt(len(access.organization_path)),
                assistant_name=self._assistant_name,
                language=self._language,
            ),
            workspace_backends=ReadOnlyWorkspaceBackends(
                tenant=self._workspace_backends(shared[0]),
                organization=tuple(self._workspace_backends(item) for item in shared[1:]),
            ),
            skill_catalog=skill_catalog,
            business_data_tool=data_tool,
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
