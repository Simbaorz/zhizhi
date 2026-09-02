"""Explicit deployment policies shared by 致知 processes."""

from pydantic import Field

from gewu_core.config import ApolloBootstrapSettings, BootstrapSettings


class ZhizhiBootstrapSettings(ApolloBootstrapSettings):
    """Explicit bootstrap policies shared by Zhizhi processes."""

    auto_create_schema: bool = Field(default=True, alias="AUTO_CREATE_SCHEMA")
    instance_namespace: str = Field(
        default="default",
        min_length=1,
        pattern=r"^[A-Za-z0-9_.-]+$",
        alias="INSTANCE_NAMESPACE",
    )
    enforce_strong_secrets: bool = Field(
        default=True,
        alias="ENFORCE_STRONG_SECRETS",
    )


def should_auto_create_schema(bootstrap: BootstrapSettings) -> bool:
    """Resolve the explicit schema startup policy."""

    return bool(getattr(bootstrap, "auto_create_schema", True))


def resolve_instance_namespace(bootstrap: BootstrapSettings) -> str:
    """Return the deployment namespace used for shared infrastructure keys."""

    value = str(getattr(bootstrap, "instance_namespace", "default")).strip()
    return value or "default"


def should_enforce_strong_secrets(bootstrap: BootstrapSettings) -> bool:
    """Resolve explicit startup secret validation.

    Zhizhi process settings default this policy to enabled. The fallback only
    applies to framework-level BootstrapSettings used by embedded runtimes.
    """

    return bool(getattr(bootstrap, "enforce_strong_secrets", False))
