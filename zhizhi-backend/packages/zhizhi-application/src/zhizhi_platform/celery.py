"""Celery transport policy scoped by an explicit Zhizhi instance namespace."""

from gewu_core.redis import RedisMode, RedisSettings


def celery_transport_options(
    settings: RedisSettings,
    *,
    project_name: str,
    instance_namespace: str,
) -> dict[str, object]:
    """Build bounded Kombu Redis options for one explicit namespace."""

    options: dict[str, object] = {
        "global_keyprefix": (f"{project_name}:{instance_namespace}:celery:"),
        **settings.client_options(),
        "retry_on_timeout": False,
    }
    connection = settings.connection
    if connection is None or connection.mode is not RedisMode.SENTINEL:
        return options
    options["master_name"] = connection.master_name
    if connection.min_other_sentinels:
        options["min_other_sentinels"] = connection.min_other_sentinels
    sentinel_options: dict[str, object] = {
        **settings.client_options(),
        "retry_on_timeout": False,
    }
    if connection.sentinel_password:
        sentinel_options["password"] = connection.sentinel_password
    options["sentinel_kwargs"] = sentinel_options
    return options
