"""Authenticated MCP query endpoint with authoritative scope and source rechecks."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl
from starlette.applications import Starlette

from gewu_core.errors import ApplicationError
from zhizhi_platform.data_source.ports import DataSourceOrganizationDirectory
from zhizhi_platform.data_source.query import DataQueryService
from zhizhi_platform.data_source.repository import DataSourceRepository
from zhizhi_platform.data_source.resolution import DataSourceResolver
from zhizhi_platform.data_source.settings import DataMcpServerSettings
from zhizhi_platform.iam import AccessScope, OrganizationUnitRef, ScopeType


class GrantVerifier:
    def __init__(self, settings: DataMcpServerSettings) -> None:
        self.settings = settings

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = jwt.decode(
                token,
                self.settings.signing_key.get_secret_value(),
                algorithms=["HS256"],
                audience=f"zhizhi-data-mcp/{self.settings.server_id}",
                issuer="zhizhi",
                options={
                    "require": [
                        "exp",
                        "iat",
                        "source_id",
                        "connection_revision",
                        "resource",
                        "mode",
                    ]
                },
            )
            if claims["resource"] != self.settings.public_url or claims["mode"] not in {
                "query",
                "probe",
            }:
                return None
            return AccessToken(
                token=token,
                client_id="zhizhi",
                scopes=["query"],
                expires_at=claims["exp"],
                resource=claims["resource"],
                claims=claims,
            )
        except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
            return None


def create_server_app(
    repository: DataSourceRepository,
    organizations: DataSourceOrganizationDirectory,
    queries: DataQueryService,
    settings: DataMcpServerSettings,
) -> Starlette:
    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
        await queries.start()
        try:
            yield None
        finally:
            await queries.close()

    server = MCPServer(
        "Zhizhi Data",
        lifespan=lifespan,
        token_verifier=GrantVerifier(settings),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(settings.public_url),
            resource_server_url=AnyHttpUrl(settings.public_url),
            required_scopes=["query"],
            validate_token_resource=True,
        ),
    )

    @server.tool(
        name="query_business_data",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        structured_output=True,
    )
    async def query_business_data(
        source_id: str, sql: str, parameters: dict[str, Any], purpose: str
    ) -> dict[str, Any]:
        """Execute bounded read-only SQL on a source authorized by the Host's signed grant."""
        token = get_access_token()
        claims = token.claims if token else None
        if not claims or claims.get("source_id") != source_id:
            raise ValueError("The request is not authorized for this source.")
        source = await repository.get_source(source_id)
        if (
            source is None
            or source.server_id != settings.server_id
            or source.connection_revision != claims.get("connection_revision")
        ):
            raise ValueError("Source configuration changed; refresh the binding before querying.")
        if claims["mode"] == "probe":
            result = await queries.execute(
                source.model_copy(update={"status": "active"}),
                "SELECT 1 AS connected",
                {},
                "connection_test",
            )
            return {"connected": result["row_count"] == 1}
        tenant_id = str(claims.get("tenant_id") or "")
        unit_id = str(claims.get("organization_unit_id") or "")
        tenant = await organizations.get_tenant(tenant_id)
        if tenant is None or tenant.status != "active":
            raise ValueError("Caller tenant is unavailable.")
        path = await organizations.get_organization_path(tenant_id, unit_id) if unit_id else ()
        if unit_id and (
            not path or any(unit.status != "active" or unit.tenant_id != tenant_id for unit in path)
        ):
            raise ValueError("Caller organization is unavailable.")
        scope = AccessScope(
            tenant_id=tenant_id,
            scope_type=ScopeType.ORGANIZATION_UNIT if unit_id else ScopeType.TENANT,
            organization_path=tuple(
                OrganizationUnitRef(id=unit.id, external_key=unit.external_key) for unit in path
            ),
        )
        try:
            selection = await DataSourceResolver(repository).resolve(scope)
        except ApplicationError as exc:
            raise ToolError("Source authorization or binding is unavailable.") from exc
        if selection is None or source_id not in {item.id for item in selection.sources}:
            raise ValueError("Source authorization or binding was revoked.")
        if len(purpose) > 512 or not purpose.strip():
            raise ValueError("A bounded query purpose is required.")
        try:
            return await queries.execute(source, sql, parameters, purpose)
        except (ValueError, TimeoutError) as exc:
            raise ToolError(str(exc) or "Query or connection admission timed out.") from exc

    public = urlsplit(settings.public_url)
    hosts = [public.netloc]
    default_port = 443 if public.scheme == "https" else 80
    if public.port in (None, default_port):
        hostname = public.hostname or ""
        authority = f"[{hostname}]" if ":" in hostname else hostname
        hosts = [authority, f"{authority}:{default_port}"]
    return server.streamable_http_app(
        streamable_http_path=public.path or "/",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=hosts,
            allowed_origins=[f"{public.scheme}://{host}" for host in hosts],
        ),
    )
