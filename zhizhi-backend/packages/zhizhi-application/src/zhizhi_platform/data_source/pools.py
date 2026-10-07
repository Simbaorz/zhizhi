"""Lazy, capacity-bounded async database engines with leased generation draining."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncEngine

from zhizhi_platform.data_source.domain import DataSourceConfig
from zhizhi_platform.data_source.settings import DataMcpServerSettings


@dataclass
class _Pool:
    engine: AsyncEngine
    capacity: int
    active: int = 0
    last_used: float = 0
    draining: bool = False


class DataSourcePools:
    def __init__(
        self, factory: Callable[[DataSourceConfig], AsyncEngine], settings: DataMcpServerSettings
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._pools: dict[tuple[str, int], _Pool] = {}
        self._condition = asyncio.Condition()
        self._closing = False
        self._latest_revision: dict[str, int] = {}

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple({key[0] for key in self._pools})

    async def _dispose(self, key: tuple[str, int]) -> None:
        pool = self._pools[key]
        await pool.engine.dispose()
        del self._pools[key]

    @asynccontextmanager
    async def lease(self, source: DataSourceConfig) -> AsyncIterator[AsyncEngine]:
        key = (source.id, source.connection_revision)
        if source.pool_size > self._settings.max_pool_capacity:
            raise ValueError("Source pool capacity exceeds this MCP process's budget.")
        async with asyncio.timeout(source.pool_timeout_seconds):
            async with self._condition:
                while True:
                    if self._closing:
                        raise RuntimeError("Data-source service is shutting down.")
                    if source.connection_revision < self._latest_revision.get(source.id, 0):
                        raise RuntimeError(
                            "Source configuration is stale; refresh it before querying."
                        )
                    self._latest_revision[source.id] = source.connection_revision
                    for old_key, old in tuple(self._pools.items()):
                        if old_key[0] == source.id and old_key != key:
                            old.draining = True
                            if not old.active:
                                await self._dispose(old_key)
                    pool = self._pools.get(key)
                    if pool is not None and not pool.draining:
                        break
                    used = sum(item.capacity for item in self._pools.values())
                    if (
                        len(self._pools) < self._settings.max_active_pools
                        and used + source.pool_size <= self._settings.max_pool_capacity
                    ):
                        pool = _Pool(self._factory(source), source.pool_size, last_used=monotonic())
                        self._pools[key] = pool
                        break
                    idle = sorted(
                        (item.last_used, item_key)
                        for item_key, item in self._pools.items()
                        if not item.active
                    )
                    if idle:
                        await self._dispose(idle[0][1])
                        continue
                    await self._condition.wait()
                pool.active += 1
        try:
            yield pool.engine
        finally:
            # Cancellation of the query must not interrupt lease accounting/disposal.
            async def release() -> None:
                async with self._condition:
                    pool.active -= 1
                    pool.last_used = monotonic()
                    if pool.draining and not pool.active and key in self._pools:
                        await self._dispose(key)
                    self._condition.notify_all()

            await asyncio.shield(release())

    async def retire(self, source_id: str, revision: int | None = None) -> None:
        async with self._condition:
            for key, pool in tuple(self._pools.items()):
                if key[0] == source_id and (revision is None or key[1] != revision):
                    pool.draining = True
                    if not pool.active:
                        await self._dispose(key)
            self._condition.notify_all()

    async def reap(self) -> None:
        async with self._condition:
            for key, pool in tuple(self._pools.items()):
                if (
                    not pool.active
                    and monotonic() - pool.last_used >= self._settings.idle_pool_seconds
                ):
                    await self._dispose(key)
            self._condition.notify_all()

    async def close(self) -> None:
        async with self._condition:
            self._closing = True
            for pool in self._pools.values():
                pool.draining = True
            self._condition.notify_all()
            async with asyncio.timeout(self._settings.shutdown_timeout_seconds):
                await self._condition.wait_for(
                    lambda: not any(pool.active for pool in self._pools.values())
                )
            for key in tuple(self._pools):
                await self._dispose(key)
