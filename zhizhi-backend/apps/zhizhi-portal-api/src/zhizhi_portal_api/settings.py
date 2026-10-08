"""Test Portal configuration with explicit reuse of platform infrastructure settings."""

import os
from pathlib import Path

from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from gewu_core.config import SettingsModel, flatten_yaml_settings, load_settings_from_values
from gewu_core.database.engine import build_async_engine_kwargs
from gewu_core.database.url import resolve_async_db_url
from gewu_core.http.settings import PasswordTransportSettings
from zhizhi_platform import ZhizhiBootstrapSettings, ZhizhiDatabaseSettings


class PortalBootstrapSettings(ZhizhiBootstrapSettings):
    config_file: Path = Field(default=Path("conf/portal.yml"), alias="CONFIG_FILE")


class PortalSettings(SettingsModel):
    platform_config_file: str = "conf/admin.yml"
    database_file: str = "var/portal/portal.db"
    agent_api_url: str = "http://127.0.0.1:8000"
    cookie_secure: bool = True
    session_hours: int = Field(default=12, ge=1, le=168)
    max_image_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)


class PortalProcessSettings(SettingsModel):
    portal: PortalSettings = Field(default_factory=PortalSettings)


def platform_infrastructure(
    settings: PortalSettings, home: Path
) -> tuple[AsyncEngine, PasswordTransportSettings]:
    # This is application startup configuration consumption, never a public API response.
    source = Path(settings.platform_config_file)
    if not source.is_absolute():
        source = home / source
    values = flatten_yaml_settings(source.read_text(), source=source.name)
    database = load_settings_from_values(
        ZhizhiDatabaseSettings,
        {key.removeprefix("db."): value for key, value in values.items() if key.startswith("db.")},
        environ={
            key.removeprefix("DB_"): value
            for key, value in os.environ.items()
            if key.startswith("DB_")
        },
    )
    transport = load_settings_from_values(
        PasswordTransportSettings,
        {
            key.removeprefix("password_transport."): value
            for key, value in values.items()
            if key.startswith("password_transport.")
        },
        environ={
            key.removeprefix("PASSWORD_TRANSPORT_"): value
            for key, value in os.environ.items()
            if key.startswith("PASSWORD_TRANSPORT_")
        },
    )
    engine = create_async_engine(
        resolve_async_db_url(database, home), **build_async_engine_kwargs(database)
    )
    return engine, transport
