from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from zhizhi_web_api import runtime as runtime_module
from zhizhi_web_api.app import create_app
from zhizhi_web_api.runtime import ZhizhiApiRuntime
from zhizhi_web_api.settings import WebApiBootstrapSettings, WebApiSettings


class _Service:
    max_image_bytes = 1024

    def __init__(self) -> None:
        self.contexts: list[Any] = []

    async def capabilities(self, context: Any) -> object:
        self.contexts.append(context)
        return {
            "support_vision": True,
            "max_image_bytes": 1024,
            "max_images_per_message": 4,
            "accepted_mime_types": ["image/jpeg", "image/png"],
        }

    async def list_messages(self, context: Any, **_kwargs: Any) -> object:
        self.contexts.append(context)
        return {"conversation_id": context.conversation_id, "messages": []}

    async def state(self, context: Any) -> object:
        self.contexts.append(context)
        return {"conversation_id": context.conversation_id, "pending_ask": None}

    async def upload_attachment(self, command: Any) -> Any:
        self.contexts.append(command)
        return SimpleNamespace(
            attachment_id="attachment-1",
            conversation_id=command.conversation_id,
            original_name="test.png",
            mime_type="image/png",
            size_bytes=1,
        )


class _Catalog:
    def __init__(self) -> None:
        self.contexts: list[Any] = []

    async def list_skills(self, context: Any) -> tuple[object, ...]:
        self.contexts.append(context)
        return ()

    async def list_scenes(self, context: Any) -> tuple[object, ...]:
        self.contexts.append(context)
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
                "tenant_code": "tenant-1",
                "active_organization_unit_id": "team-1",
                "principal_id": "user-1",
                "principal_type": "user",
            },
        )

    assert response.status_code == 200
    assert response.json()["support_vision"] is True


@pytest.mark.parametrize("organization_id", [None, "", "team-1"])
def test_initial_load_accepts_optional_active_organization(organization_id: str | None) -> None:
    service = _Service()
    catalog = _Catalog()
    app = create_app(service=cast(Any, service), catalog=catalog)
    params = {"tenant_code": "tenant-1", "principal_id": "user-1", "principal_type": "user"}
    if organization_id is not None:
        params["active_organization_unit_id"] = organization_id
    with TestClient(app) as client:
        for path in (
            "/api/agent/capabilities",
            "/api/agent/skills",
            "/api/agent/scenes",
            "/api/agent/conversations/conversation-1/messages",
            "/api/agent/conversations/conversation-1/pending-ask",
        ):
            response = client.get(path, params=params)
            assert response.status_code == 200, (path, response.json())
    contexts = service.contexts + catalog.contexts
    assert len(contexts) == 5
    assert all(
        context.active_organization_unit_id == (organization_id or "") for context in contexts
    )
    assert all(
        context.tenant_code == "tenant-1" and context.principal_id == "user-1"
        for context in contexts
    )
    assert service.contexts[-1].conversation_id == "conversation-1"


@pytest.mark.parametrize("missing", ["tenant_code", "principal_id", "principal_type"])
def test_optional_organization_does_not_make_caller_identity_optional(missing: str) -> None:
    app = create_app(service=cast(Any, _Service()), catalog=_Catalog())
    params = {"tenant_code": "tenant-1", "principal_id": "user-1", "principal_type": "user"}
    del params[missing]
    with TestClient(app) as client:
        assert client.get("/api/agent/capabilities", params=params).status_code == 422


@pytest.mark.parametrize("organization_id", [None, "", "team-1"])
def test_attachment_upload_accepts_optional_active_organization(
    organization_id: str | None,
) -> None:
    service = _Service()
    app = create_app(service=cast(Any, service), catalog=_Catalog())
    data = {
        "conversation_id": "conversation-1",
        "tenant_code": "tenant-1",
        "principal_id": "user-1",
        "principal_type": "user",
        "request_id": "request-1",
    }
    if organization_id is not None:
        data["active_organization_unit_id"] = organization_id
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/chat/attachments",
            data=data,
            files={"file": ("test.png", b"test", "image/png")},
        )
    assert response.status_code == 200, response.json()
    assert service.contexts[0].active_organization_unit_id == (organization_id or "")


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
