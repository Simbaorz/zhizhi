from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from gewu_agent_runtime.llm import ScriptedChatModel
from gewu_agent_runtime.workspace import InMemoryWorkspaceBackend
from gewu_core.config import load_settings
from zhizhi.runtime_capabilities import ZhizhiCapabilityResolver
from zhizhi.scope import AgentScope
from zhizhi_web_api.settings import AgentSettings, WebApiBootstrapSettings, WebApiSettings


@pytest.mark.parametrize(
    ("agent_yaml", "name", "language"),
    [
        ("", "致知", "zh-CN"),
        ('agent:\n  assistant_name: "企业知识助手"\n  language: en-US\n', "企业知识助手", "en-US"),
    ],
)
async def test_yaml_agent_identity_reaches_resolved_prompt(
    tmp_path: Path, agent_yaml: str, name: str, language: str
) -> None:
    config = tmp_path / "web.yml"
    config.write_text(
        "workspace:\n  storage_root: volume/workspace\n"
        "media:\n  root: volume/media\n" + agent_yaml,
        encoding="utf-8",
    )
    settings = load_settings(
        WebApiSettings,
        WebApiBootstrapSettings(PROJECT_HOME=tmp_path, CONFIG_FILE=config),
        environ={},
    )
    assert settings.agent.assistant_name == name
    assert settings.agent.language == language

    class Models:
        async def resolve(self, _scope):
            return SimpleNamespace(model=ScriptedChatModel([]))

    class Catalogs:
        async def resolve(self, _scope):
            return None, None

    resolver = ZhizhiCapabilityResolver(
        models=Models(),
        catalogs=Catalogs(),
        workspace_backends=lambda _scope: InMemoryWorkspaceBackend(),
        assistant_name=settings.agent.assistant_name,
        language=settings.agent.language,
    )
    capabilities = await resolver.resolve(
        AgentScope(
            tenant_id="tenant",
            tenant_code="TENANT",
            tenant_storage_key="tenant",
            principal_id="user",
        )
    )
    assert capabilities.prompt.full.startswith(f"You are {name},")
    assert f"# Current User Language\n\n- Language: {language}" in capabilities.prompt.full
    assert "/workspace/tenant" in capabilities.prompt.full


@pytest.mark.parametrize("language", ["", None, 42])
def test_invalid_language_is_rejected(language: object) -> None:
    with pytest.raises(ValidationError):
        AgentSettings.model_validate({"language": language})
