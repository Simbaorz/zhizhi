from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from zhizhi_web_api import runtime as runtime_module
from zhizhi_web_api.app import create_app
from zhizhi_web_api.runtime import ZhizhiApiRuntime
from zhizhi_web_api.settings import WebApiBootstrapSettings, WebApiSettings


class _Service:
    async def capabilities(self, context: Any) -> object:
        del context
        return {
            "support_vision": True,
            "max_image_bytes": 1024,
            "max_images_per_message": 4,
            "accepted_mime_types": ["image/jpeg", "image/png"],
        }


class _Catalog:
    async def list_skills(self, context: Any) -> tuple[object, ...]:
        return ()

    async def list_scenes(self, context: Any) -> tuple[object, ...]:
        return ()


def test_agent_api_exposes_only_embedded_workbench_surface() -> None:
    app = create_app(service=cast(Any, _Service()), catalog=_Catalog())
    paths = set(app.openapi()["paths"])

    assert "/api/agent/chat/stream" in paths
    assert "/api/agent/chat/ask-answer" in paths
    assert "/api/agent/capabilities" in paths
    assert "/api/agent/chat/attachments" in paths
    assert "/api/agent/chat/attachments/{attachment_id}" in paths
    assert "/api/agent/conversations/{conversation_id}/messages" in paths
    assert "/api/agent/conversations/{conversation_id}/pending-ask" in paths
    assert "/api/agent/conversations/{conversation_id}/interrupt" in paths
    assert not any("login" in path or "workspace" in path for path in paths)
    assert not any(path.endswith("/conversations") for path in paths)


def test_injected_app_health_and_readiness_do_not_require_process_resources() -> None:
    app = create_app(service=cast(Any, _Service()), catalog=_Catalog())

    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/readyz").json() == {"status": "ready"}


def test_capabilities_use_the_trusted_tenant_and_principal_scope() -> None:
    app = create_app(service=cast(Any, _Service()), catalog=_Catalog())

    with TestClient(app) as client:
        response = client.get(
            "/api/agent/capabilities",
            params={
                "tenant_id": "tenant-1",
                "active_organization_unit_id": "team-1",
                "principal_id": "user-1",
                "principal_type": "user",
            },
        )

    assert response.status_code == 200
    assert response.json()["support_vision"] is True


async def test_web_runtime_loads_apollo_once_without_monitoring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    settings = WebApiSettings(
        workspace={"storage_root": str(tmp_path / "workspace")},
        media={"root": str(tmp_path / "media")},
    )

    async def load_once(*_args: object, **_kwargs: object) -> WebApiSettings:
        events.append("load")
        return settings

    bootstrap = WebApiBootstrapSettings(
        PROJECT_HOME=tmp_path,
        CONFIG_SOURCE="apollo",
        APOLLO_BASE_URL="http://apollo.test",
        APOLLO_APP_ID="zhizhi-web-api",
    )
    runtime = ZhizhiApiRuntime(bootstrap)

    async def start_components(resolved: WebApiSettings) -> None:
        assert resolved is settings
        runtime._started = True

    monkeypatch.setattr(runtime_module, "load_settings_once", load_once)
    monkeypatch.setattr(runtime, "_startup_components", start_components)

    await runtime.startup()
    await runtime.shutdown()

    assert runtime.settings is settings
    assert events == ["load"]
