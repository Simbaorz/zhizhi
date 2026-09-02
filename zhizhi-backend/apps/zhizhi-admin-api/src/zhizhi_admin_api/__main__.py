"""Run the dedicated 致知 Admin API process."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from typing import Any, cast

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gewu_core.apollo_config import load_settings_once
from gewu_core.config import load_bootstrap_settings_as
from gewu_core.database import build_async_engine_kwargs, resolve_async_db_url
from gewu_core.http.runner import run_http_service
from zhizhi_admin_api.settings import AdminApiBootstrapSettings, AdminApiSettings
from zhizhi_platform.iam import (
    AdminSeedError,
    SuperAdminBootstrapInput,
    initialize_super_admin,
    seed_admin_security,
    super_admin_exists,
)
from zhizhi_platform.schema import ensure_schema_for_mode


def main() -> None:
    """Run the management-facing 致知 ASGI application."""

    if sys.argv[1:2] == ["init-super-admin"]:
        _run_init_super_admin_command(sys.argv[2:])
        return
    run_http_service(
        "zhizhi_admin_api.app:app",
        "Run the 致知 management API service.",
    )


def _run_init_super_admin_command(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Create the one-time super admin account.")
    parser.add_argument("--username", default="", help="Super admin username.")
    parser.add_argument("--password", default="", help="Super admin password.")
    parser.add_argument("--display-name", default="", help="Super admin display name.")
    args = parser.parse_args(arguments)
    try:
        asyncio.run(
            _init_super_admin(
                username=args.username,
                password=args.password,
                display_name=args.display_name,
            )
        )
    except AdminSeedError as exc:
        raise SystemExit(f"failed to initialize super admin: {exc.detail}") from exc


def _resolve_super_admin_cli_input(
    *,
    username: str,
    password: str,
    display_name: str,
) -> tuple[str, str, str]:
    resolved_username = username.strip() or input("Super admin username: ").strip()
    resolved_password = password or getpass.getpass("Super admin password: ")
    if not password:
        repeated_password = getpass.getpass("Confirm super admin password: ")
        if resolved_password != repeated_password:
            raise SystemExit("failed to initialize super admin: passwords do not match")
    return resolved_username, resolved_password, display_name.strip() or "超级管理员"


async def _init_super_admin(username: str, password: str, display_name: str) -> None:
    bootstrap = load_bootstrap_settings_as(AdminApiBootstrapSettings)
    settings = await load_settings_once(
        AdminApiSettings,
        bootstrap,
        required_paths=("redis.connection",),
    )
    if not settings.db.enabled:
        raise AdminSeedError(500, "db.enabled/db.url is not configured.")
    db_url = resolve_async_db_url(settings.db, bootstrap.project_home)
    engine = create_async_engine(
        db_url,
        **cast(dict[str, Any], build_async_engine_kwargs(settings.db, use_null_pool=True)),
    )
    try:
        await ensure_schema_for_mode(engine, bootstrap.mode)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        if await super_admin_exists(sessions):
            print("super admin already exists")  # noqa: T201
            return
        resolved = _resolve_super_admin_cli_input(
            username=username,
            password=password,
            display_name=display_name,
        )
        bootstrap_input = SuperAdminBootstrapInput(
            username=resolved[0],
            password=resolved[1],
            display_name=resolved[2],
        )
        await seed_admin_security(sessions)
        user = await initialize_super_admin(sessions, bootstrap_input)
        print(f"super admin initialized: {user.username}")  # noqa: T201
        print(f"username: {user.username}")  # noqa: T201
        print(f"password: {bootstrap_input.password}")  # noqa: T201
    finally:
        await engine.dispose()


if __name__ == "__main__":
    main()
