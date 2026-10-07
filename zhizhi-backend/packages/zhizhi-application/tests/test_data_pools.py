from __future__ import annotations

import asyncio
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from zhizhi_platform.data_source.domain import DataSourceConfig
from zhizhi_platform.data_source.pools import DataSourcePools
from zhizhi_platform.data_source.settings import DataMcpServerSettings


class FakeEngine:
    disposed = False

    async def dispose(self) -> None:
        self.disposed = True


def config(key: str, **values) -> DataSourceConfig:
    return DataSourceConfig(
        id=key,
        source_key=key,
        tag=key.upper(),
        host="db",
        database="db",
        username="reader",
        pool_size=1,
        **values,
    )


async def test_pools_are_lazy_reused_and_revision_change_drains_inflight_queries() -> None:
    created: list[FakeEngine] = []

    def factory(_source: DataSourceConfig) -> AsyncEngine:
        engine = FakeEngine()
        created.append(engine)
        return cast(AsyncEngine, engine)

    pools = DataSourcePools(factory, DataMcpServerSettings(max_pool_capacity=2, max_active_pools=2))
    assert created == []
    async with pools.lease(config("orders")) as first:
        async with pools.lease(config("orders")) as same:
            assert first is same
        async with pools.lease(config("orders", connection_revision=2)) as new:
            assert new is not first
            assert not created[0].disposed
        assert not created[0].disposed
    assert created[0].disposed
    with pytest.raises(RuntimeError):
        async with pools.lease(config("orders")):
            pass
    await pools.close()
    assert all(engine.disposed for engine in created)


async def test_capacity_waits_for_leases_and_evicts_only_idle_pools() -> None:
    created: list[FakeEngine] = []

    def factory(_source: DataSourceConfig) -> AsyncEngine:
        engine = FakeEngine()
        created.append(engine)
        return cast(AsyncEngine, engine)

    pools = DataSourcePools(factory, DataMcpServerSettings(max_pool_capacity=1, max_active_pools=1))
    async with pools.lease(config("orders")):
        with pytest.raises(TimeoutError):
            async with pools.lease(config("customers", pool_timeout_seconds=0.01)):
                pass
        assert not created[0].disposed
    async with pools.lease(config("customers")):
        assert created[0].disposed
    await pools.close()


async def test_cancelled_waiter_does_not_leak_capacity() -> None:
    pools = DataSourcePools(
        lambda _source: cast(AsyncEngine, FakeEngine()), DataMcpServerSettings(max_pool_capacity=1)
    )
    async with pools.lease(config("orders")):

        async def wait() -> None:
            async with pools.lease(config("other")):
                pass

        task = asyncio.create_task(wait())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    async with pools.lease(config("other")):
        pass
    await pools.close()
