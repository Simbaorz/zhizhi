from pathlib import Path

from gewu_core.config import load_settings
from zhizhi_admin_api.settings import AdminApiBootstrapSettings, AdminApiSettings
from zhizhi_platform.workspace import resolve_workspace_storage_root
from zhizhi_web_api.settings import WebApiBootstrapSettings, WebApiSettings
from zhizhi_worker.settings import ZhizhiWorkerBootstrapSettings, ZhizhiWorkerSettings


def test_tracked_example_configs_match_current_settings_models() -> None:
    project_home = Path(__file__).parents[2]
    config_dir = project_home / "conf"

    admin_settings = load_settings(
        AdminApiSettings,
        AdminApiBootstrapSettings(
            PROJECT_HOME=project_home,
            CONFIG_FILE=config_dir / "admin.example.yml",
        ),
        environ={},
        required_paths=("redis.connection",),
    )
    web_settings = load_settings(
        WebApiSettings,
        WebApiBootstrapSettings(
            PROJECT_HOME=project_home,
            CONFIG_FILE=config_dir / "web.example.yml",
        ),
        environ={},
        required_paths=("redis.connection", "workspace.storage_root"),
    )
    worker_settings = load_settings(
        ZhizhiWorkerSettings,
        ZhizhiWorkerBootstrapSettings(
            PROJECT_HOME=project_home,
            CONFIG_FILE=config_dir / "worker.example.yml",
        ),
        environ={},
        required_paths=("redis.connection",),
    )

    assert isinstance(admin_settings, AdminApiSettings)
    assert isinstance(web_settings, WebApiSettings)
    assert isinstance(worker_settings, ZhizhiWorkerSettings)

    expected_workspace_root = (project_home / "volume/workspace").resolve()
    assert (
        resolve_workspace_storage_root(admin_settings.workspace.storage_root, project_home)
        == expected_workspace_root
    )
    assert (
        resolve_workspace_storage_root(web_settings.workspace.storage_root, project_home)
        == expected_workspace_root
    )
    assert (
        resolve_workspace_storage_root(worker_settings.workspace.storage_root, project_home)
        == expected_workspace_root
    )
    assert admin_settings.runtime.temp_dir == "volume/temp"
    assert web_settings.runtime.temp_dir == "volume/temp"
    assert worker_settings.runtime.temp_dir == "volume/temp"
    assert web_settings.media.root == "volume/media"
    assert worker_settings.media.root == "volume/media"
    assert admin_settings.password_transport.private_key_path == "conf/admin-password-key.pem"
