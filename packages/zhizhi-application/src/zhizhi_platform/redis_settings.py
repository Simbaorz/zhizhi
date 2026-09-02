"""Redis configuration required by 致知 processes."""

from typing import Literal

from pydantic import Field

from gewu_core.redis import RedisConnectionSettings, RedisMode, RedisSettings


class ZhizhiRedisSettings(RedisSettings):
    """Redis settings that cannot be disabled by a 致知 application."""

    enabled: Literal[True] = True
    connection: RedisConnectionSettings = Field(
        default_factory=lambda: RedisConnectionSettings(
            mode=RedisMode.STANDALONE,
            host="127.0.0.1",
        )
    )
