"""Exact Zhizhi prompt preset over subscriber-neutral Runtime inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from gewu_agent_runtime.prompts import (
    PromptProfile,
    SystemPrompt,
    WorkspacePromptContext,
    build_system_prompt,
    get_static_prompt,
)

ZHIZHI_ASSISTANT_NAME = "Zhizhi"
ZHIZHI_DYNAMIC_BOUNDARY = "__ZHIZHI_PROMPT_DYNAMIC_BOUNDARY__"
ZHIZHI_MEMORY_INTRODUCTION = """\
# Memory

Bot.md and User.md are persistent profile documents from the user's private
workspace, automatically loaded into context. They contain project-specific
instructions and user preferences that persist across sessions.
"""


def build_zhizhi_prompt_profile(
    *,
    bot_md: str = "",
    user_md: str = "",
) -> PromptProfile | None:
    """Project Zhizhi's Bot.md/User.md records into neutral prompt sections."""

    if not bot_md and not user_md:
        return None
    sections = [ZHIZHI_MEMORY_INTRODUCTION]
    if bot_md:
        sections.append(f"<BotInfo>\n{bot_md}\n</BotInfo>\n")
    if user_md:
        sections.append(f"<UserInfo>\n{user_md}\n</UserInfo>\n")
    return PromptProfile(sections=("\n\n".join(sections),))


def get_zhizhi_static_prompt(
    assistant_name: str = ZHIZHI_ASSISTANT_NAME,
) -> str:
    """Return the byte-compatible static prompt for the Zhizhi subscriber."""

    return get_static_prompt(_resolve_zhizhi_assistant_name(assistant_name))


def build_zhizhi_system_prompt(
    *,
    profile: PromptProfile | None = None,
    workspace: WorkspacePromptContext | None = None,
    extra_dynamic_sections: Mapping[str, str] | Sequence[str] | None = None,
    assistant_name: str = ZHIZHI_ASSISTANT_NAME,
) -> SystemPrompt:
    """Build the exact Zhizhi prompt while keeping the Runtime default neutral."""

    return build_system_prompt(
        profile=profile,
        workspace=workspace,
        extra_dynamic_sections=extra_dynamic_sections,
        assistant_name=_resolve_zhizhi_assistant_name(assistant_name),
        dynamic_boundary=ZHIZHI_DYNAMIC_BOUNDARY,
    )


def _resolve_zhizhi_assistant_name(value: str) -> str:
    return value.strip() or ZHIZHI_ASSISTANT_NAME
