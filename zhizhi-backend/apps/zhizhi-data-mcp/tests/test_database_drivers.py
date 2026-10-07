"""Optional isolated live-driver checks; never use a deployment's real credentials."""

from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gewu_core import JsonSecretCipher
from zhizhi_platform.data_source.domain import DataSourceConfig
from zhizhi_platform.data_source.query import DataQueryService
from zhizhi_platform.data_source.repository import DataSourceRepository
from zhizhi_platform.data_source.settings import DataMcpServerSettings


@pytest.mark.parametrize("driver", ["mysql", "postgresql"])
async def test_database_driver_uses_read_only_transactions_and_bounded_results(driver: str) -> None:
    value = os.environ.get(f"ZHIZHI_TEST_{driver.upper()}_PORT")
    if not value:
        pytest.skip("Requires a disposable localhost-only database container.")
    port = int(value)
    key = "test-encryption-key" * 2
    source = DataSourceConfig(
        id=driver,
        source_key=driver,
        tag="TEST",
        driver=driver,
        host="127.0.0.1",
        port=port,
        database="zhizhi_query_test",
        username="root" if driver == "mysql" else "postgres",
        credentials_ciphertext=JsonSecretCipher(key).encrypt({"password": "zhizhi-test-only"}),
        max_rows=2,
    )
    setup = create_async_engine(
        URL.create(
            "mysql+asyncmy" if driver == "mysql" else "postgresql+asyncpg",
            username=source.username,
            password="zhizhi-test-only",
            host=source.host,
            port=source.port,
            database=source.database,
        )
    )
    for attempt in range(30):
        try:
            async with setup.begin() as connection:
                await connection.exec_driver_sql("DROP TABLE IF EXISTS orders")
                await connection.exec_driver_sql(
                    "CREATE TABLE orders (id INTEGER PRIMARY KEY, amount INTEGER)"
                )
                await connection.exec_driver_sql(
                    "INSERT INTO orders VALUES (1, 10), (2, 20), (3, 30)"
                )
            break
        except Exception:
            if attempt == 29:
                raise
            await asyncio.sleep(0.5)
    platform = create_async_engine("sqlite+aiosqlite:///:memory:")
    service = DataQueryService(
        DataSourceRepository(async_sessionmaker(platform)), DataMcpServerSettings(), key
    )
    try:
        result = await service.execute(
            source,
            "SELECT id, amount FROM orders WHERE amount >= :minimum ORDER BY id",
            {"minimum": 10},
            "Check bounded query",
        )
        assert result["rows"] == [{"id": 1, "amount": 10}, {"id": 2, "amount": 20}]
        assert result["truncated"] is True
        sql = (
            "SELECT @@transaction_read_only AS read_only"
            if driver == "mysql"
            else "SELECT current_setting('transaction_read_only') AS read_only"
        )
        state = await service.execute(source, sql, {}, "Check database read-only state")
        assert state["rows"][0]["read_only"] in (1, "on")
    finally:
        await service.close()
        await platform.dispose()
        await setup.dispose()
