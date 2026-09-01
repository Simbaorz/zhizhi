"""Zhizhi Admin one-time super-user CLI behavior."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from zhizhi_admin_api.__main__ import _init_super_admin
from zhizhi_platform.iam import ADMIN_PERMISSION_SEEDS, verify_password
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminPermissionModel,
    AdminUserModel,
)


async def test_init_super_admin_command_round_trip(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    config = tmp_path / "conf.yml"
    config.write_text(
        "db:\n"
        "  enabled: true\n"
        "  use_sqlite: true\n"
        "redis:\n"
        "  connection:\n"
        "    mode: standalone\n"
        "    host: redis.internal\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECT_HOME", str(tmp_path))
    monkeypatch.setenv("CONFIG_FILE", str(config))

    await _init_super_admin("root", "root-pass", "Root Admin")
    first_output = capsys.readouterr().out
    await _init_super_admin("ignored", "ignored", "Ignored")
    second_output = capsys.readouterr().out

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            users = list(session.scalars(select(AdminUserModel)))
            permissions = list(session.scalars(select(AdminPermissionModel)))
    finally:
        engine.dispose()

    assert "super admin initialized: root" in first_output
    assert "username: root" in first_output
    assert "password: root-pass" in first_output
    assert second_output == "super admin already exists\n"
    assert len(users) == 1
    assert users[0].is_super
    assert verify_password("root-pass", users[0].password_hash)
    assert len(permissions) == len(ADMIN_PERMISSION_SEEDS)


def test_cli_input_rejects_mismatched_prompt_passwords(monkeypatch) -> None:
    from zhizhi_admin_api import __main__ as cli

    monkeypatch.setattr("builtins.input", lambda prompt: "root")
    passwords = iter(("first", "second"))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(passwords))

    try:
        cli._resolve_super_admin_cli_input(username="", password="", display_name="")
    except SystemExit as exc:
        error = exc
    else:
        error = None

    assert error is not None
    assert str(error) == "failed to initialize super admin: passwords do not match"
