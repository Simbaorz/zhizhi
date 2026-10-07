"""Start local Docker dependencies using the application's existing connection settings."""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pymysql
import redis
import yaml
from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url

from gewu_core.config import flatten_yaml_settings, load_settings_from_values
from zhizhi_platform import ZhizhiDatabaseSettings, ZhizhiRedisSettings

LOCAL_HOSTS = {"localhost", "127.0.0.1"}


@dataclass
class LocalDependencies:
    mysql: URL | None = field(default=None, repr=False)
    redis_connection: tuple[int, str] | None = field(default=None, repr=False)

    def compose_environment(self, environment: Mapping[str, str]) -> dict[str, str]:
        values = dict(environment)
        values["ZHIZHI_LOCAL_MYSQL_ROOT_PASSWORD"] = secrets.token_urlsafe(32)
        if self.mysql is not None:
            source = self.mysql
            # Keep initialization settings stable so repeated starts reuse the container.
            values["ZHIZHI_LOCAL_MYSQL_ROOT_PASSWORD"] = source.password or ""
            values["ZHIZHI_LOCAL_MYSQL_PORT"] = str(source.port or 3306)
            values["ZHIZHI_LOCAL_MYSQL_DATABASE"] = source.database or "zhizhi"
            if source.username == "root":
                values["ZHIZHI_LOCAL_MYSQL_USER"] = ""
                values["ZHIZHI_LOCAL_MYSQL_PASSWORD"] = ""
            else:
                values["ZHIZHI_LOCAL_MYSQL_USER"] = source.username or ""
                values["ZHIZHI_LOCAL_MYSQL_PASSWORD"] = source.password or ""
        if self.redis_connection is not None:
            port, password = self.redis_connection
            values["ZHIZHI_LOCAL_REDIS_PORT"] = str(port)
            values["ZHIZHI_LOCAL_REDIS_PASSWORD"] = password
        return values

    def verify_connections(self) -> None:
        if self.mysql is not None:
            source = self.mysql
            with pymysql.connect(
                host="127.0.0.1",
                port=source.port or 3306,
                user=source.username,
                password=source.password,
                database=source.database,
                connect_timeout=5,
                read_timeout=5,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    if cursor.fetchone() != (1,):
                        raise RuntimeError("MySQL connection verification failed.")
            print(f"MySQL ready: 127.0.0.1:{source.port or 3306}", flush=True)
        if self.redis_connection is not None:
            port, password = self.redis_connection
            with redis.Redis(
                host="127.0.0.1",
                port=port,
                password=password or None,
                socket_connect_timeout=5,
                socket_timeout=5,
            ) as connection:
                if not connection.ping():
                    raise RuntimeError("Redis connection verification failed.")
            print(f"Redis ready: 127.0.0.1:{port}", flush=True)


def resolve_dependencies(root: Path, environment: Mapping[str, str]) -> LocalDependencies:
    dependencies = LocalDependencies()
    for name in ("admin", "web", "worker", "data-mcp"):
        path = root / "conf" / f"{name}.yml"
        if name == "data-mcp" and environment.get("DATA_MCP_ENABLED", "false").lower() not in {
            "true",
            "1",
        }:
            continue
        if not path.is_file():
            if name == "data-mcp":
                raise ValueError("Missing local Data MCP configuration.")
            raise ValueError(f"Missing local {name} configuration.")
        configuration = yaml.safe_load(path.read_text()) or {}
        db = load_settings_from_values(
            ZhizhiDatabaseSettings,
            flatten_yaml_settings(yaml.safe_dump(configuration.get("db", {})), source=path.name),
            environ={
                key.removeprefix("DB_"): value
                for key, value in environment.items()
                if key.startswith("DB_")
            },
        )
        if db.enabled and not db.use_sqlite:
            source = make_url(db.url)
            if source.host in LOCAL_HOSTS and source.get_backend_name() == "mysql":
                if not source.username or not source.password or not source.database:
                    raise ValueError(
                        "Local MySQL requires a configured username, password and database."
                    )
                if dependencies.mysql is not None and source != dependencies.mysql:
                    raise ValueError("Local processes must use the same MySQL connection settings.")
                dependencies.mysql = source
        if name == "data-mcp":
            continue
        settings = load_settings_from_values(
            ZhizhiRedisSettings,
            flatten_yaml_settings(yaml.safe_dump(configuration.get("redis", {})), source=path.name),
            environ={
                key.removeprefix("REDIS_"): value
                for key, value in environment.items()
                if key.startswith("REDIS_")
            },
        )
        source_redis = settings.connection
        if (
            settings.enabled
            and source_redis.mode == "standalone"
            and source_redis.host in LOCAL_HOSTS
        ):
            connection_settings = (source_redis.port, source_redis.password)
            if (
                dependencies.redis_connection is not None
                and dependencies.redis_connection != connection_settings
            ):
                raise ValueError("Local processes must use the same Redis port and password.")
            dependencies.redis_connection = connection_settings
    return dependencies


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    environment = dict(os.environ)
    for name in (".env", ".env.local"):
        environment.update(
            {key: value for key, value in dotenv_values(root / name).items() if value is not None}
        )
    try:
        dependencies = resolve_dependencies(root, environment)
        services = []
        if dependencies.mysql is not None:
            services.append("mysql")
        if dependencies.redis_connection is not None:
            services.append("redis")
        if services and not arguments.verify_only:
            for service in services:
                subprocess.run(
                    ["docker", "volume", "create", f"zhizhi-{service}-data"],
                    stdout=subprocess.DEVNULL,
                    check=True,
                )
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(root / "docker" / "compose.local.yml"),
                    "up",
                    "--detach",
                    "--wait",
                    "--wait-timeout",
                    "120",
                    *services,
                ],
                env=dependencies.compose_environment(environment),
                check=True,
            )
        dependencies.verify_connections()
        if not services:
            print("No local MySQL/Redis dependencies configured; Docker startup skipped.")
    except Exception as exc:
        # Driver/YAML exceptions may contain credentials; never echo their text.
        raise SystemExit(
            f"Local dependency startup failed ({type(exc).__name__}). Check Docker, local connection settings "
            "and existing volume credentials. Data volumes have not been reset."
        ) from None


if __name__ == "__main__":
    main()
