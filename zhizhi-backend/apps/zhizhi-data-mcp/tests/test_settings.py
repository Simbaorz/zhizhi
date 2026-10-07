"""Deployment examples expose complete settings for the process that uses them."""

from pathlib import Path

import pytest
import yaml

from gewu_core.config import flatten_yaml_settings, load_settings_from_values
from zhizhi_admin_api.settings import AdminApiSettings
from zhizhi_data_mcp.app import DataMcpProcessSettings
from zhizhi_web_api.settings import WebApiSettings

CONFIG_DIRECTORY = Path(__file__).resolve().parents[4] / "conf"


def example(name: str) -> dict:
    return yaml.safe_load((CONFIG_DIRECTORY / f"{name}.example.yml").read_text())


@pytest.mark.parametrize(
    ("name", "settings_type"),
    [("admin", AdminApiSettings), ("web", WebApiSettings), ("data-mcp", DataMcpProcessSettings)],
)
def test_examples_load_and_list_every_database_and_mcp_field(name, settings_type) -> None:
    values = example(name)
    settings = load_settings_from_values(
        settings_type,
        flatten_yaml_settings(yaml.safe_dump(values), source=f"{name}.example.yml"),
        environ={
            "DATA_MCP_ENABLED": "true",
            "DATA_MCP_SIGNING_KEY": "s" * 32,
            "STORAGE_ENCRYPTION_KEY": "e" * 32,
        },
    )
    assert set(values["db"]) == set(type(settings.db).model_fields)
    assert set(values["data_mcp"]) == set(type(settings.data_mcp).model_fields)


@pytest.mark.parametrize("settings_type", [AdminApiSettings, WebApiSettings])
@pytest.mark.parametrize("field", ["server_id", "public_url", "max_pool_capacity"])
def test_clients_reject_unused_server_settings(settings_type, field) -> None:
    with pytest.raises(ValueError, match="Unknown configuration keys"):
        load_settings_from_values(settings_type, {f"data_mcp.{field}": "unused"}, environ={})


@pytest.mark.parametrize("field", ["token_ttl_seconds", "max_client_connections"])
def test_server_rejects_unused_client_settings(field) -> None:
    with pytest.raises(ValueError, match="Unknown configuration keys"):
        load_settings_from_values(DataMcpProcessSettings, {f"data_mcp.{field}": 60}, environ={})


@pytest.mark.parametrize("name", ["admin", "web"])
def test_environment_overrides_client_lifetime(name) -> None:
    settings_type = AdminApiSettings if name == "admin" else WebApiSettings
    settings = load_settings_from_values(
        settings_type,
        flatten_yaml_settings(yaml.safe_dump(example(name)), source=f"{name}.example.yml"),
        environ={"DATA_MCP_TOKEN_TTL_SECONDS": "120"},
    )
    assert settings.data_mcp.token_ttl_seconds == 120
