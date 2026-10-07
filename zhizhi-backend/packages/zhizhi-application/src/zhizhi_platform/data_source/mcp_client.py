"""Official MCP SDK client with request-scoped signed grants and shared HTTP pooling."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from contextvars import ContextVar
from time import time
from typing import Any

import httpx2
import jwt
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from zhizhi_platform.data_source.domain import DataSourceConfig
from zhizhi_platform.data_source.settings import DataMcpClientSettings
from zhizhi_platform.iam import AccessScope

_grant: ContextVar[str] = ContextVar("zhizhi_mcp_query_grant", default="")


class _GrantAuth(httpx2.Auth):
    def auth_flow(
        self, request: httpx2.Request
    ) -> Generator[httpx2.Request, httpx2.Response, None]:
        token = _grant.get()
        if not token:
            raise RuntimeError("MCP request has no trusted source grant.")
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


class DataMcpClient:
    def __init__(
        self, settings: DataMcpClientSettings, *, http_client: httpx2.AsyncClient | None = None
    ) -> None:
        self.settings = settings
        self._owned = http_client is None
        self.http = http_client or httpx2.AsyncClient(
            auth=_GrantAuth(),
            follow_redirects=False,
            limits=httpx2.Limits(
                max_connections=settings.max_client_connections,
                max_keepalive_connections=min(20, settings.max_client_connections),
            ),
            # The per-query asyncio deadline owns read timing; SQL may legitimately run >10s.
            timeout=httpx2.Timeout(None, connect=5, pool=5, write=10),
        )

    async def query(
        self,
        source: DataSourceConfig,
        scope: AccessScope | None,
        sql: str,
        parameters: dict[str, Any],
        purpose: str,
        *,
        probe: bool = False,
    ) -> dict[str, Any]:
        if not self.settings.enabled:
            raise RuntimeError("data_mcp must be enabled and configured before querying.")
        if not probe and scope is None:
            raise ValueError("Queries require trusted caller scope.")
        issued_at = int(time())
        claims = {
            "iss": "zhizhi",
            "aud": f"zhizhi-data-mcp/{source.server_id}",
            "exp": issued_at + self.settings.token_ttl_seconds,
            "iat": issued_at,
            "source_id": source.id,
            "connection_revision": source.connection_revision,
            "resource": source.endpoint_url,
            "mode": "probe" if probe else "query",
            "tenant_id": scope.tenant_id if scope else "",
            "organization_unit_id": (
                scope.organization_path[-1].id if scope and scope.organization_path else ""
            ),
            "principal_id": scope.principal_id if scope else "admin-probe",
        }
        token = jwt.encode(claims, self.settings.signing_key.get_secret_value(), algorithm="HS256")
        handle = _grant.set(token)
        try:
            async with asyncio.timeout(
                source.query_timeout_seconds
                + source.pool_timeout_seconds
                + source.connect_timeout_seconds
                + 10
            ):
                # HTTP connections are process-scoped; SDK transports and their grants are request-scoped.
                async with Client(
                    streamable_http_client(source.endpoint_url, http_client=self.http)
                ) as client:
                    tools = await client.list_tools()
                    tool = next(
                        (tool for tool in tools.tools if tool.name == "query_business_data"), None
                    )
                    if tool is None or not {"source_id", "sql", "parameters", "purpose"}.issubset(
                        tool.input_schema.get("properties", {})
                    ):
                        raise RuntimeError(
                            "MCP server does not expose the expected query_business_data contract."
                        )
                    result = await client.call_tool(
                        "query_business_data",
                        {
                            "source_id": source.id,
                            "sql": sql,
                            "parameters": parameters,
                            "purpose": purpose,
                        },
                    )
                # Validate after the SDK transport closes so expected tool errors are not
                # wrapped by nested AnyIO task-group exception groups.
                if result.is_error or not isinstance(result.structured_content, dict):
                    raise RuntimeError("MCP query failed or returned an invalid structured result.")
                return dict(result.structured_content)
        finally:
            _grant.reset(handle)

    async def close(self) -> None:
        if self._owned:
            await self.http.aclose()
