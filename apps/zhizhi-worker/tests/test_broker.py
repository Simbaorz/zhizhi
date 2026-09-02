"""致知 Celery broker policy parity."""

from __future__ import annotations

import pytest

from gewu_core.redis import (
    RedisClientSettings,
    RedisConnectionSettings,
    RedisDatabasesSettings,
    RedisMode,
    RedisSettings,
)
from zhizhi_worker.broker import celery_broker_url, celery_transport_options


def test_standalone_broker_uses_celery_database_and_url_encoded_password() -> None:
    settings = RedisSettings(
        enabled=True,
        connection=RedisConnectionSettings(
            mode=RedisMode.STANDALONE,
            host="redis.internal",
            password="p@ss/word",
        ),
        databases=RedisDatabasesSettings(celery=7),
    )

    assert celery_broker_url(settings) == "redis://:p%40ss%2Fword@redis.internal:6379/7"


def test_sentinel_broker_and_transport_options_match_application_contract() -> None:
    settings = RedisSettings(
        enabled=True,
        connection=RedisConnectionSettings(
            mode=RedisMode.SENTINEL,
            nodes=["redis-sentinel-1:26379", "redis-sentinel-2:26379"],
            master_name="mymaster",
            redis_password="redis-secret",
            sentinel_password="sentinel-secret",
            min_other_sentinels=1,
        ),
        client=RedisClientSettings(
            max_connections=21,
            socket_timeout_seconds=4.0,
            socket_connect_timeout_seconds=2.0,
            socket_keepalive=False,
            health_check_interval_seconds=15,
        ),
    )

    assert celery_broker_url(settings) == (
        "sentinel://:redis-secret@redis-sentinel-1:26379;"
        "sentinel://:redis-secret@redis-sentinel-2:26379"
    )
    assert celery_transport_options(
        settings,
        project_name="zhizhi",
        mode="test",
    ) == {
        "global_keyprefix": "zhizhi:test:celery:",
        "max_connections": 21,
        "socket_timeout": 4.0,
        "socket_connect_timeout": 2.0,
        "socket_keepalive": False,
        "health_check_interval": 15,
        "retry_on_timeout": False,
        "master_name": "mymaster",
        "min_other_sentinels": 1,
        "sentinel_kwargs": {
            "password": "sentinel-secret",
            "max_connections": 21,
            "socket_timeout": 4.0,
            "socket_connect_timeout": 2.0,
            "socket_keepalive": False,
            "health_check_interval": 15,
            "retry_on_timeout": False,
        },
    }


def test_broker_fails_closed_for_disabled_redis_cluster_and_sentinel_database() -> None:
    with pytest.raises(RuntimeError, match="must be enabled"):
        celery_broker_url(RedisSettings())

    cluster = RedisSettings(
        enabled=True,
        connection=RedisConnectionSettings(
            mode=RedisMode.CLUSTER,
            nodes=["redis-cluster:6379"],
        ),
        databases=RedisDatabasesSettings(app=0),
    )
    with pytest.raises(RuntimeError, match="Cluster"):
        celery_broker_url(cluster)

    sentinel = RedisSettings(
        enabled=True,
        connection=RedisConnectionSettings(
            mode=RedisMode.SENTINEL,
            nodes=["redis-sentinel:26379"],
            master_name="mymaster",
        ),
        databases=RedisDatabasesSettings(celery=1),
    )
    with pytest.raises(RuntimeError, match="database 0"):
        celery_broker_url(sentinel)
