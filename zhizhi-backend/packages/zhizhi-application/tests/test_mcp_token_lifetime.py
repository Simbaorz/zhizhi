"""Token lifetime is a caller setting shared by queries and Admin probes."""

from types import SimpleNamespace

import jwt
import pytest

from zhizhi_platform.data_source import mcp_client
from zhizhi_platform.data_source.domain import DataSourceConfig
from zhizhi_platform.data_source.settings import DataMcpClientSettings
from zhizhi_platform.iam import AccessScope, ScopeType


@pytest.mark.parametrize("ttl", [60, 180])
@pytest.mark.parametrize("probe", [False, True])
async def test_every_call_mints_a_new_token_using_configured_lifetime(
    monkeypatch, ttl, probe
) -> None:
    tokens = []

    class Client:
        def __init__(self, transport):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(
                        name="query_business_data",
                        input_schema={
                            "properties": {
                                field: {} for field in ("source_id", "sql", "parameters", "purpose")
                            }
                        },
                    )
                ]
            )

        async def call_tool(self, name, arguments):
            tokens.append(mcp_client._grant.get())
            return SimpleNamespace(is_error=False, structured_content={"connected": True})

    monkeypatch.setattr(mcp_client, "Client", Client)
    now = [1700000000]
    monkeypatch.setattr(mcp_client, "time", lambda: now[0])
    settings = DataMcpClientSettings(enabled=True, signing_key="k" * 32, token_ttl_seconds=ttl)
    client = mcp_client.DataMcpClient(settings)
    source = DataSourceConfig(
        id="orders", source_key="orders", tag="OB", host="db", database="orders", username="reader"
    )
    scope = None if probe else AccessScope(tenant_id="tenant", scope_type=ScopeType.TENANT)
    try:
        for _ in range(2):
            await client.query(source, scope, "SELECT 1", {}, "Check token", probe=probe)
            now[0] += ttl + 1
    finally:
        await client.close()
    claims = [
        jwt.decode(
            token,
            "k" * 32,
            algorithms=["HS256"],
            audience="zhizhi-data-mcp/main",
            options={"verify_exp": False},
        )
        for token in tokens
    ]
    assert all(claim["exp"] - claim["iat"] == ttl for claim in claims)
    assert claims[1]["iat"] > claims[0]["exp"]
    assert all(claim["mode"] == ("probe" if probe else "query") for claim in claims)


def test_token_lifetime_defaults_to_sixty_seconds_and_must_be_positive() -> None:
    assert DataMcpClientSettings().token_ttl_seconds == 60
    with pytest.raises(ValueError):
        DataMcpClientSettings(token_ttl_seconds=0)
