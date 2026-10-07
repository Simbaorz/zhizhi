"""Check local dependency selection without reading deployment files or starting Docker."""

import importlib
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def launcher(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("local_dependencies")


def write_configs(root, *, db=None, redis=None):
    directory = root / "conf"
    directory.mkdir()
    redis_settings = redis or {"enabled": False}
    configuration = {
        "db": db or {"use_sqlite": True},
        "redis": {
            **redis_settings,
            "connection": {
                "mode": "standalone",
                "host": "127.0.0.1",
                "port": 6379,
                **redis_settings.get("connection", {}),
            },
        },
    }
    for name in ("admin", "web", "worker"):
        (directory / f"{name}.yml").write_text(yaml.safe_dump(configuration))


def test_sqlite_and_remote_redis_do_not_start_local_containers(tmp_path, launcher):
    write_configs(tmp_path, redis={"enabled": True, "connection": {"host": "redis.example.test"}})
    dependencies = launcher.resolve_dependencies(tmp_path, {})
    assert dependencies.mysql is None
    assert dependencies.redis_connection is None


def test_environment_overrides_select_local_connections(tmp_path, launcher):
    write_configs(tmp_path)
    environment = {
        "DB_USE_SQLITE": "false",
        "DB_URL": "mysql+aiomysql://reader:test-only@127.0.0.1:3307/zhizhi",
        "REDIS_ENABLED": "true",
        "REDIS_CONNECTION_PORT": "6380",
        "REDIS_CONNECTION_PASSWORD": "test-only",
    }
    dependencies = launcher.resolve_dependencies(tmp_path, environment)
    assert dependencies.mysql.port == 3307
    assert dependencies.redis_connection == (6380, "test-only")
    assert "test-only" not in repr(dependencies)
    first = dependencies.compose_environment(environment)
    second = dependencies.compose_environment(environment)
    assert first == second


@pytest.mark.parametrize("kind", ["mysql", "redis"])
def test_conflicting_local_credentials_are_rejected_before_starting_docker(
    tmp_path, launcher, kind
):
    db = {
        "use_sqlite": False,
        "url": "mysql+aiomysql://reader:test-only@127.0.0.1/zhizhi",
    }
    redis = {
        "enabled": True,
        "connection": {
            "mode": "standalone",
            "host": "127.0.0.1",
            "port": 6379,
            "password": "test-only",
        },
    }
    write_configs(tmp_path, db=db, redis=redis)
    changed = {"db": db, "redis": redis}
    if kind == "mysql":
        changed["db"] = {
            **db,
            "url": "mysql+aiomysql://reader:different-test-only@127.0.0.1/zhizhi",
        }
    else:
        changed["redis"] = {
            "enabled": True,
            "connection": {
                "mode": "standalone",
                "host": "127.0.0.1",
                "port": 6379,
                "password": "different-test-only",
            },
        }
    (tmp_path / "conf" / "worker.yml").write_text(yaml.safe_dump(changed))
    with pytest.raises(ValueError) as caught:
        launcher.resolve_dependencies(tmp_path, {})
    assert "test-only" not in str(caught.value)


def test_optional_data_mcp_uses_platform_mysql_without_adding_redis(tmp_path, launcher):
    db = {
        "use_sqlite": False,
        "url": "mysql+aiomysql://reader:test-only@127.0.0.1/zhizhi",
    }
    write_configs(
        tmp_path,
        db=db,
        redis={"enabled": True, "connection": {"password": "test-only"}},
    )
    (tmp_path / "conf" / "data-mcp.yml").write_text(yaml.safe_dump({"db": db}))
    dependencies = launcher.resolve_dependencies(tmp_path, {"DATA_MCP_ENABLED": "true"})
    assert dependencies.mysql is not None
    assert dependencies.redis_connection == (6379, "test-only")
