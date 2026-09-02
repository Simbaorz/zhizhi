"""Worker command-line compatibility behavior."""

from __future__ import annotations

from zhizhi_worker import __main__ as cli


class _FakeCeleryApp:
    def __init__(self) -> None:
        self.arguments: list[str] | None = None

    def start(self, arguments: list[str]) -> None:
        self.arguments = arguments


def test_windows_worker_defaults_to_solo_pool(monkeypatch) -> None:
    app = _FakeCeleryApp()
    monkeypatch.setattr(cli, "create_celery_app", lambda: app)
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["zhizhi-worker", "worker", "--loglevel=DEBUG"],
    )

    cli.main()

    assert app.arguments == ["worker", "--pool", "solo", "--loglevel=DEBUG"]


def test_explicit_windows_worker_pool_is_preserved(monkeypatch) -> None:
    app = _FakeCeleryApp()
    monkeypatch.setattr(cli, "create_celery_app", lambda: app)
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["zhizhi-worker", "worker", "--pool=threads", "--loglevel=INFO"],
    )

    cli.main()

    assert app.arguments == ["worker", "--pool=threads", "--loglevel=INFO"]


def test_non_windows_worker_keeps_celery_platform_default(monkeypatch) -> None:
    app = _FakeCeleryApp()
    monkeypatch.setattr(cli, "create_celery_app", lambda: app)
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["zhizhi-worker", "worker", "--loglevel=INFO"],
    )

    cli.main()

    assert app.arguments == ["worker", "--loglevel=INFO"]


def test_pool_argument_detection_matches_celery_forms() -> None:
    explicit_forms: tuple[list[str], ...] = (
        ["-P", "threads"],
        ["-Pthreads"],
        ["--pool", "threads"],
        ["--pool=threads"],
    )

    assert all(cli._has_celery_pool_arg(arguments) for arguments in explicit_forms)
    assert not cli._has_celery_pool_arg(["--loglevel=INFO"])
