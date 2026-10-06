from __future__ import annotations

from gewu_agent_runtime import AgentRuntime, PrincipalRef, PrincipalType, TurnBindings, TurnRequest
from gewu_agent_runtime.builtins import SceneDocument
from gewu_agent_runtime.invocation import InvocationTarget, InvocationTargetKind
from gewu_agent_runtime.llm import ModelStreamChunk, ScriptedChatModel
from gewu_agent_runtime.persistence import InMemoryRuntimeStore
from gewu_agent_runtime.prompts import WorkspacePromptContext
from gewu_agent_runtime.workspace import InMemoryWorkspaceBackend
from zhizhi.capabilities import ReadOnlyWorkspaceBackends, build_read_only_workspace
from zhizhi.runtime_capabilities import _workspace_prompt
from zhizhi_platform.prompt import (
    ZHIZHI_DYNAMIC_BOUNDARY,
    build_zhizhi_prompt_profile,
    build_zhizhi_system_prompt,
    get_zhizhi_static_prompt,
)


def test_knowledge_prompt_uses_only_supplied_context() -> None:
    prompt = build_zhizhi_system_prompt(workspace=_workspace_prompt(2))

    assert prompt.full.startswith(get_zhizhi_static_prompt())
    assert "Wiki" in prompt.full
    assert "The workspace is read-only" in prompt.full
    assert "Do not discover or switch Scenes autonomously" in prompt.full
    assert "## Scenes" in prompt.full
    assert "/workspace/tenant" in prompt.full
    assert "/workspace/organization-2" in prompt.full
    assert "Writable:\n- None" in prompt.full
    for title in (
        "# Memory",
        "# Default Scene",
        "# Available Scenes",
        "# Environment",
        "# Current User Language",
    ):
        assert title not in prompt.full
    assert "Use `edit`" not in prompt.full


def test_empty_context_omits_titles_and_memory_profile() -> None:
    assert build_zhizhi_prompt_profile(bot_md=" \n ", user_md="") is None
    prompt = build_zhizhi_system_prompt(
        workspace=WorkspacePromptContext(), extra_dynamic_sections=(" \n ",)
    )
    assert prompt.dynamic_sections == (ZHIZHI_DYNAMIC_BOUNDARY,)
    assert "# Workspace" not in prompt.full


def test_explicit_context_precedes_memory_and_prefix_is_stable() -> None:
    profile = build_zhizhi_prompt_profile(user_md="Use concise answers.")
    extras = ("# Default Scene\n\nEntry path: /workspace/tenant/.scenes/policies",)
    prompt = build_zhizhi_system_prompt(
        workspace=_workspace_prompt(0),
        profile=profile,
        extra_dynamic_sections=extras,
        assistant_name="Wiki Assistant",
    )

    assert prompt.full.startswith(get_zhizhi_static_prompt("Wiki Assistant"))
    assert prompt.full.index("# Workspace") < prompt.full.index("# Default Scene")
    assert prompt.full.index("# Default Scene") < prompt.full.index("# Memory")
    assert "Use concise answers." in prompt.full
    assert "private workspace" not in prompt.full
    assert prompt == build_zhizhi_system_prompt(
        workspace=_workspace_prompt(0),
        profile=profile,
        extra_dynamic_sections=extras,
        assistant_name="Wiki Assistant",
    )


async def test_runtime_receives_knowledge_rules_and_only_the_selected_scene() -> None:
    scene = SceneDocument(
        asset_key="policies",
        name="Policies",
        workspace_path="/workspace/tenant/.scenes/policies",
    )

    class SelectedSceneCatalog:
        async def get_scene(self, asset_key: str) -> SceneDocument | None:
            return scene if asset_key == scene.asset_key else None

    model = ScriptedChatModel([[ModelStreamChunk(content_delta="done")]])
    workspace = build_read_only_workspace(
        ReadOnlyWorkspaceBackends(tenant=InMemoryWorkspaceBackend())
    )
    session = await AgentRuntime(store=InMemoryRuntimeStore()).start_turn(
        TurnRequest(
            invoker=PrincipalRef(
                subscriber_id="zhizhi", principal_id="user", principal_type=PrincipalType.USER
            ),
            content="Read the policy",
            invocation_target=InvocationTarget(
                kind=InvocationTargetKind.SCENE, resource_id=scene.asset_key
            ),
        ),
        TurnBindings(
            model=model,
            workspace=workspace,
            scene_catalog=SelectedSceneCatalog(),
            prompt=build_zhizhi_system_prompt(workspace=_workspace_prompt(0)),
        ),
    )
    async for _event in session.stream():
        pass

    request = model.requests[0][0]
    assert request[0].role.value == "system"
    assert "Wiki" in request[0].content
    assert "The workspace is read-only" in request[0].content
    assert "# Available Scenes" not in request[0].content
    context = "\n".join(message.content for message in request[1:])
    assert "<system-reminder>" in context
    assert scene.workspace_path in context
