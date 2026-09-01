"""External-service substitutes scoped to Admin API tests."""

from __future__ import annotations

import pytest

from gewu_core.redis import RedisSettings
from zhizhi_admin_api import runtime as admin_runtime


class TestRedisClient:
    """Small Redis substitute covering Admin login-throttle commands."""

    __test__ = False

    def __init__(self, settings: RedisSettings) -> None:
        self.settings = settings
        self.initialized = False
        self._values: dict[str, object] = {}
        self._ttls: dict[str, int] = {}

    @property
    def connection(self) -> TestRedisClient:
        return self

    async def initialize(self) -> None:
        self.initialized = True

    async def close(self) -> None:
        self.initialized = False

    async def get(self, key: str) -> object:
        return self._values.get(key)

    async def incr(self, key: str) -> int:
        value = int(self._values.get(key, 0)) + 1
        self._values[key] = value
        return value

    async def expire(self, key: str, seconds: int) -> bool:
        if key not in self._values:
            return False
        self._ttls[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        if key not in self._values:
            return -2
        return self._ttls.get(key, -1)

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            deleted += int(self._values.pop(key, None) is not None)
            self._ttls.pop(key, None)
        return deleted


@pytest.fixture(autouse=True)
def use_test_redis_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Admin lifecycle tests independent of an external Redis service."""

    monkeypatch.setattr(admin_runtime, "RedisClient", TestRedisClient)
