"""Run the dedicated 致知 Celery process."""

from __future__ import annotations

import sys

from zhizhi_worker.celery_app import create_celery_app


def main() -> None:
    """Forward worker or beat arguments to the configured Celery application."""

    create_celery_app().start(_default_celery_args(sys.argv[1:]))


def _default_celery_args(arguments: list[str]) -> list[str]:
    """Apply the Windows-safe worker pool default."""

    resolved = list(arguments)
    if (
        resolved[:1] == ["worker"]
        and sys.platform == "win32"
        and not _has_celery_pool_arg(resolved[1:])
    ):
        resolved[1:1] = ["--pool", "solo"]
    return resolved


def _has_celery_pool_arg(arguments: list[str]) -> bool:
    """Return whether the caller explicitly selected a Celery worker pool."""

    return any(
        argument in {"-P", "--pool"} or argument.startswith("-P") or argument.startswith("--pool=")
        for argument in arguments
    )


if __name__ == "__main__":
    main()
