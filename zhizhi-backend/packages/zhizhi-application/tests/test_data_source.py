from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gewu_agent_runtime.tools import ToolContext
from gewu_agent_runtime.workspace import InMemoryWorkspaceBackend
from gewu_core.errors import ApplicationError
from zhizhi.business_data_tool import build_business_data_tool
from zhizhi.capabilities import ReadOnlyWorkspaceBackends, build_read_only_workspace
from zhizhi_platform.data_source.domain import DataSourceConfig, SourceBinding, SourceEntitlement
from zhizhi_platform.data_source.repository import DataSourceRepository
from zhizhi_platform.data_source.resolution import DataSourceResolver
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import AccessScope, OrganizationUnitRef, ScopeType


async def test_nearest_binding_routes_only_authorized_tags_and_default(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sources.db'}")
    repository = DataSourceRepository(async_sessionmaker(engine, expire_on_commit=False))
    async with engine.begin() as connection:
        await connection.run_sync(ZhizhiBase.metadata.create_all)
    one = await repository.save_source(
        DataSourceConfig(
            source_key="orders", tag="OB", host="db", database="orders", username="reader"
        )
    )
    two = await repository.save_source(
        DataSourceConfig(
            source_key="analytics", tag="ADB", host="db", database="analytics", username="reader"
        )
    )
    for unit in ("", "division", "leaf"):
        for source in (one, two):
            await repository.save_entitlement(
                SourceEntitlement(
                    tenant_id="tenant", organization_unit_id=unit, source_id=source.id
                )
            )
    await repository.save_binding(
        SourceBinding(tenant_id="tenant", source_ids=(one.id,), default_source_id=one.id)
    )
    await repository.save_binding(
        SourceBinding(
            tenant_id="tenant",
            organization_unit_id="division",
            source_ids=(one.id, two.id),
            default_source_id=two.id,
        )
    )
    scope = AccessScope(
        tenant_id="tenant",
        scope_type=ScopeType.ORGANIZATION_UNIT,
        organization_path=(
            OrganizationUnitRef(id="division", external_key="division"),
            OrganizationUnitRef(id="leaf", external_key="leaf"),
        ),
    )
    selection = await DataSourceResolver(repository).resolve(scope)
    assert selection is not None
    assert selection.default_tag == "ADB"
    assert {source.tag for source in selection.sources} == {"OB", "ADB"}
    calls = []

    class Client:
        async def query(self, source, caller, sql, parameters, purpose):
            calls.append((source.id, caller.tenant_id, sql, parameters))
            return {"rows": [{"value": 7}], "data_source_tag": source.tag}

    tool = build_business_data_tool(selection, DataSourceResolver(repository), Client(), scope)
    assert tool.input_schema["properties"]["data_source_tag"]["enum"] == ["ADB", "OB"]
    assert "source_id" not in tool.input_schema["properties"]
    workspace = build_read_only_workspace(
        ReadOnlyWorkspaceBackends(tenant=InMemoryWorkspaceBackend())
    )
    context = ToolContext(conversation_id="conversation", run_id="run", workspace=workspace)
    result = await tool.execute(
        {
            "sql": "SELECT :value",
            "parameters": {"value": 7},
            "purpose": "Read Wiki-selected data",
            "data_source_tag": "OB",
        },
        context,
    )
    assert not result.is_error and calls[-1][0] == one.id
    await tool.execute({"sql": "SELECT 1", "purpose": "Default data"}, context)
    assert calls[-1][0] == two.id
    before = len(calls)
    invalid = await tool.execute(
        {"sql": "SELECT 1", "purpose": "Invalid tag", "data_source_tag": "MISSING"}, context
    )
    assert invalid.is_error and len(calls) == before
    assert (
        await DataSourceResolver(repository).resolve(
            scope.model_copy(update={"tenant_id": "other"})
        )
        is None
    )
    entitlement = await repository.get_entitlement("tenant", "leaf", one.id)
    assert entitlement is not None
    await repository.delete_entitlement(entitlement.id)
    revoked = await tool.execute(
        {"sql": "SELECT 1", "purpose": "Revoked source", "data_source_tag": "OB"}, context
    )
    assert revoked.is_error and len(calls) == before
    with pytest.raises(ApplicationError):
        await DataSourceResolver(repository).resolve(scope)
    await engine.dispose()


def test_source_configuration_is_bounded_and_normalizes_tags() -> None:
    source = DataSourceConfig(
        source_key="orders", tag="ob", host="db", database="orders", username="reader"
    )
    assert source.tag == "OB"
    for values in (
        {"pool_size": 0},
        {"pool_size": 500},
        {"driver": "shell"},
        {"endpoint_url": "file:///tmp/mcp"},
    ):
        with pytest.raises(ValueError):
            DataSourceConfig(
                source_key="orders",
                tag="OB",
                host="db",
                database="orders",
                username="reader",
                **values,
            )


async def test_unavailable_data_binding_does_not_disable_wiki_capabilities() -> None:
    from types import SimpleNamespace

    from gewu_agent_runtime.llm import ScriptedChatModel
    from zhizhi.runtime_capabilities import ZhizhiCapabilityResolver
    from zhizhi.scope import AgentScope
    from zhizhi_platform.data_source.mcp_client import DataMcpClient
    from zhizhi_platform.data_source.settings import DataMcpClientSettings

    class Models:
        async def resolve(self, _scope):
            return SimpleNamespace(model=ScriptedChatModel([]))

    class Catalogs:
        async def resolve(self, _scope):
            return None, None

    class Sources:
        async def resolve(self, _scope):
            from gewu_core.errors import ApplicationErrorKind

            raise ApplicationError(ApplicationErrorKind.FORBIDDEN, "Grant was revoked.")

    client = DataMcpClient(DataMcpClientSettings())
    try:
        resolver = ZhizhiCapabilityResolver(
            models=Models(),
            catalogs=Catalogs(),
            workspace_backends=lambda _scope: InMemoryWorkspaceBackend(),
            data_sources=Sources(),
            data_mcp_client=client,
        )
        capabilities = await resolver.resolve(
            AgentScope(
                tenant_id="tenant",
                tenant_code="TENANT",
                tenant_storage_key="tenant",
                principal_id="user",
            )
        )
        assert capabilities.business_data_tool is None
        assert capabilities.workspace_backends.tenant is not None
        assert "Wiki" in capabilities.prompt.full
    finally:
        await client.close()
