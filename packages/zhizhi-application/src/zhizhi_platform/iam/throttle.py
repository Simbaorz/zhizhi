"""Shared, bounded login failure throttling for Zhizhi identities."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from gewu_core.redis import observe_redis
from zhizhi_platform.iam.codes import canonical_stable_code
from zhizhi_platform.iam.settings import LoginThrottleSettings


class LoginThrottleDecision(BaseModel):
    """Result of checking one login attempt against failure limits."""

    model_config = ConfigDict(frozen=True)

    blocked: bool = False
    retry_after_seconds: int = 0


class LoginThrottleBackend(Protocol):
    async def retry_after(
        self,
        keys: tuple[str, str],
        *,
        max_failures: int,
    ) -> int: ...

    async def register_failure(
        self,
        keys: tuple[str, str],
        *,
        max_failures: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None: ...

    async def clear(self, key: str) -> None: ...


class MemoryLoginThrottleBackend:
    """Store bounded failure counters in the current development process."""

    def __init__(self, max_keys: int = 10_000) -> None:
        if max_keys < 1:
            raise ValueError("max_keys must be at least 1")
        self._max_keys = max_keys
        self._counters: OrderedDict[str, tuple[int, float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def retry_after(
        self,
        keys: tuple[str, str],
        *,
        max_failures: int,
    ) -> int:
        now = time.monotonic()
        async with self._lock:
            self._evict(now)
            retry_after = 0
            for key in keys:
                count, expires_at = self._counters.get(key, (0, 0.0))
                if count >= max_failures and expires_at > now:
                    retry_after = max(retry_after, int(expires_at - now) + 1)
            return retry_after

    async def register_failure(
        self,
        keys: tuple[str, str],
        *,
        max_failures: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None:
        now = time.monotonic()
        async with self._lock:
            self._evict(now)
            for key in keys:
                count, expires_at = self._counters.get(key, (0, 0.0))
                if expires_at <= now:
                    count = 0
                count += 1
                lifetime = lockout_seconds if count >= max_failures else window_seconds
                self._counters[key] = (count, now + lifetime)
                self._counters.move_to_end(key)
            while len(self._counters) > self._max_keys:
                self._counters.popitem(last=False)

    async def clear(self, key: str) -> None:
        async with self._lock:
            self._counters.pop(key, None)

    def _evict(self, now: float) -> None:
        for key in [key for key, (_, expires_at) in self._counters.items() if expires_at <= now]:
            self._counters.pop(key, None)
        while len(self._counters) >= self._max_keys:
            self._counters.popitem(last=False)


class RedisCommands(Protocol):
    async def get(self, key: str) -> object: ...

    async def incr(self, key: str) -> object: ...

    async def expire(self, key: str, seconds: int) -> object: ...

    async def ttl(self, key: str) -> object: ...

    async def delete(self, key: str) -> object: ...


class RedisLoginThrottleBackend:
    """Store login counters in one already-initialized shared Redis client."""

    def __init__(self, redis: RedisCommands) -> None:
        self._redis = redis

    async def retry_after(
        self,
        keys: tuple[str, str],
        *,
        max_failures: int,
    ) -> int:
        values = await observe_redis(
            "login.retry_after.get",
            asyncio.gather(*(self._redis.get(key) for key in keys)),
        )
        blocked = [
            key
            for key, value in zip(keys, values, strict=True)
            if _int_value(value) >= max_failures
        ]
        if not blocked:
            return 0
        ttls = await observe_redis(
            "login.retry_after.ttl",
            asyncio.gather(*(self._redis.ttl(key) for key in blocked)),
        )
        return max((max(_int_value(ttl), 1) for ttl in ttls), default=1)

    async def register_failure(
        self,
        keys: tuple[str, str],
        *,
        max_failures: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None:
        await asyncio.gather(
            *(
                self._increment(
                    key,
                    max_failures=max_failures,
                    window_seconds=window_seconds,
                    lockout_seconds=lockout_seconds,
                )
                for key in keys
            )
        )

    async def clear(self, key: str) -> None:
        await observe_redis("login.clear", self._redis.delete(key))

    async def _increment(
        self,
        key: str,
        *,
        max_failures: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None:
        count = _int_value(await observe_redis("login.failure.incr", self._redis.incr(key)))
        if count == 1:
            await observe_redis("login.failure.expire", self._redis.expire(key, window_seconds))
        if count >= max_failures:
            await observe_redis("login.lockout.expire", self._redis.expire(key, lockout_seconds))


class LoginThrottle:
    """Throttle failures by client IP and canonical Zhizhi username."""

    def __init__(
        self,
        backend: LoginThrottleBackend,
        settings: LoginThrottleSettings,
        *,
        project_name: str,
        mode: str,
        namespace: str,
    ) -> None:
        self._backend = backend
        self._settings = settings
        self._prefix = f"{project_name.strip() or 'zhizhi'}:{mode.strip() or 'dev'}:auth"
        self._namespace = namespace

    async def check(self, client_ip: str, username: str) -> LoginThrottleDecision:
        if not self._settings.enabled:
            return LoginThrottleDecision()
        retry_after = await self._backend.retry_after(
            self._keys(client_ip, username),
            max_failures=self._settings.max_failures,
        )
        return LoginThrottleDecision(
            blocked=retry_after > 0,
            retry_after_seconds=retry_after,
        )

    async def register_failure(self, client_ip: str, username: str) -> None:
        if not self._settings.enabled:
            return
        await self._backend.register_failure(
            self._keys(client_ip, username),
            max_failures=self._settings.max_failures,
            window_seconds=self._settings.window_seconds,
            lockout_seconds=self._settings.lockout_seconds,
        )

    async def register_success(self, username: str) -> None:
        if not self._settings.enabled:
            return
        await self._backend.clear(self._key("username", canonical_stable_code(username)))

    def _keys(self, client_ip: str, username: str) -> tuple[str, str]:
        return (
            self._key("ip", client_ip.strip() or "unknown"),
            self._key("username", canonical_stable_code(username)),
        )

    def _key(self, dimension: str, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"{self._prefix}:{self._namespace}:{dimension}:{digest}"


def validate_login_throttle_configuration(
    settings: LoginThrottleSettings,
    *,
    mode: str,
    redis_enabled: bool,
) -> None:
    """Require shared counters for multi-process production throttling."""

    if mode.strip().lower() == "prod" and settings.enabled and not redis_enabled:
        raise RuntimeError("Redis must be enabled for production login throttling.")


def _int_value(value: object) -> int:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
