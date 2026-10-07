"""Exercise the actual SDK client/server protocol, signed grants and live revocation."""

from __future__ import annotations

import asyncio
from time import time

import httpx2
import jwt
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gewu_core import JsonSecretCipher
from zhizhi_data_mcp.server import create_server_app
from zhizhi_platform.data_source.domain import DataSourceConfig, SourceBinding, SourceEntitlement
from zhizhi_platform.data_source.mcp_client import DataMcpClient, _GrantAuth
from zhizhi_platform.data_source.pools import DataSourcePools
from zhizhi_platform.data_source.query import DataQueryService
from zhizhi_platform.data_source.repository import DataSourceRepository
from zhizhi_platform.data_source.settings import DataMcpClientSettings, DataMcpServerSettings
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import AccessScope, ScopeType
from zhizhi_platform.iam.models import ManagedTenant


class Organizations:
    async def get_tenant(self, tenant_id: str) -> ManagedTenant | None:
        return (
            ManagedTenant(id="tenant", tenant_code="TENANT", tenant_name="Tenant")
            if tenant_id == "tenant"
            else None
        )

    async def get_organization_unit(self, unit_id: str):
        return None

    async def get_organization_path(self, tenant_id: str, unit_id: str):
        return ()

    async def descendant_ids(self, ids):
        return ()


@pytest.mark.parametrize(
    ("server_id", "public_url"),
    [
        ("main", "http://127.0.0.1:8002/mcp"),
        ("reporting", "https://data.example.test/data/mcp"),
    ],
)
async def test_official_mcp_round_trip_uses_bound_parameters_and_rechecks_grants(
    tmp_path, server_id, public_url
) -> None:
    platform = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}")
    async with platform.begin() as connection:
        await connection.run_sync(ZhizhiBase.metadata.create_all)
    business = tmp_path / "business.db"
    seed = create_async_engine(f"sqlite+aiosqlite:///{business}")
    async with seed.begin() as connection:
        await connection.exec_driver_sql(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, amount INTEGER)"
        )
        await connection.exec_driver_sql("INSERT INTO orders VALUES (1, 10), (2, 20), (3, 30)")
    await seed.dispose()
    repository = DataSourceRepository(async_sessionmaker(platform, expire_on_commit=False))
    key = "e" * 32
    settings = DataMcpServerSettings(
        enabled=True,
        signing_key="s" * 32,
        server_id=server_id,
        public_url=public_url,
    )
    source = await repository.save_source(
        DataSourceConfig(
            source_key="orders",
            tag="OB",
            host="db",
            database="orders",
            username="reader",
            server_id=settings.server_id,
            endpoint_url=settings.public_url,
            max_rows=2,
            credentials_ciphertext=JsonSecretCipher(key).encrypt(
                {"password": "test-only-password"}
            ),
        )
    )
    entitlement = await repository.save_entitlement(
        SourceEntitlement(tenant_id="tenant", source_id=source.id)
    )
    await repository.save_binding(
        SourceBinding(tenant_id="tenant", source_ids=(source.id,), default_source_id=source.id)
    )
    queries = DataQueryService(repository, settings, key)
    queries.pools = DataSourcePools(
        lambda config: create_async_engine(
            f"sqlite+aiosqlite:///{business}", pool_size=config.pool_size, max_overflow=0
        ),
        settings,
    )
    app = create_server_app(repository, Organizations(), queries, settings)
    transport = httpx2.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=transport, auth=_GrantAuth()) as http:
            client = DataMcpClient(
                DataMcpClientSettings(enabled=True, signing_key="s" * 32), http_client=http
            )
            scope = AccessScope(tenant_id="tenant", scope_type=ScopeType.TENANT)
            result = await client.query(
                source,
                scope,
                "SELECT id, amount FROM orders WHERE amount >= :minimum ORDER BY id",
                {"minimum": 10},
                "Verify orders",
            )
            assert result["rows"] == [{"id": 1, "amount": 10}, {"id": 2, "amount": 20}]
            assert result["truncated"] is True
            assert result["data_source_tag"] == "OB"
            assert "password" not in str(result)
            now = int(time())
            grant = jwt.encode(
                {
                    "iss": "zhizhi",
                    "aud": f"zhizhi-data-mcp/{server_id}",
                    "iat": now,
                    "exp": now + 60,
                    "source_id": source.id,
                    "connection_revision": source.connection_revision,
                    "resource": settings.public_url,
                    "mode": "probe",
                },
                "s" * 32,
                algorithm="HS256",
            )
            async with httpx2.AsyncClient(transport=transport) as raw:
                for headers, status in [
                    ({"Host": "unexpected.example.test"}, 421),
                    ({"Origin": "https://unexpected.example.test"}, 403),
                ]:
                    response = await raw.post(
                        settings.public_url,
                        headers={"Authorization": f"Bearer {grant}", **headers},
                        json={},
                    )
                    assert response.status_code == status
            concurrent = await asyncio.gather(
                client.query(source, scope, "SELECT 1 AS value", {}, "Allowed caller"),
                client.query(
                    source,
                    AccessScope(tenant_id="other", scope_type=ScopeType.TENANT),
                    "SELECT 1",
                    {},
                    "Other caller",
                ),
                return_exceptions=True,
            )
            assert isinstance(concurrent[0], dict)
            assert isinstance(concurrent[1], RuntimeError)
            await repository.delete_entitlement(entitlement.id)
            with pytest.raises(RuntimeError):
                await client.query(source, scope, "SELECT 1", {}, "Check revoked source")
            probe = await client.query(
                source, None, "DELETE FROM orders", {}, "ignored", probe=True
            )
            assert probe == {"connected": True}
    await platform.dispose()
