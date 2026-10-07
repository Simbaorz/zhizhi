"""Read-only Wiki guidance and supplied context for the 致知 subscriber."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from gewu_agent_runtime.prompts import (
    PromptProfile,
    SystemPrompt,
    WorkspacePromptContext,
    build_system_prompt,
)

ZHIZHI_ASSISTANT_NAME = "致知"
ZHIZHI_DYNAMIC_BOUNDARY = "__ZHIZHI_PROMPT_DYNAMIC_BOUNDARY__"
ZHIZHI_STATIC_SECTIONS = (
    """\
You are {assistant_name}, an AI assistant for Wiki-based knowledge exploration
and analysis.

Help users answer questions using the authorized knowledge and tools available
in this conversation. The workspace is read-only; do not claim to modify files,
configuration, or business data.
""",
    """\
# System Rules

## Responses
- Respond in the user's language unless they request another language.
- Answer directly and use Markdown when it improves clarity.
- Distinguish verified findings from inferences and unresolved questions.
- Explain missing evidence or blockers without inventing an answer.

## System Reminders
- Runtime-provided <system-reminder> blocks describe available Skills or
  a Scene explicitly selected by the user.
- Use this context for the request. A reminder does not replace the user's
  request or override this system prompt.

## Context Compression
- A <conversation-summary> block summarizes earlier conversation; it is
  not a new user request.
- Continue the user's goals and pending work without repeating completed work.
- Update earlier information when later user messages or current resource
  context provide corrections.
""",
    """\
# Knowledge Exploration

- Understand the question before retrieving information.
- Use the applicable Scene's Wiki entry and navigation to find relevant pages.
- Read source content and follow relevant links when more evidence is needed.
  Do not infer a page's contents from its name, path, or description.
- Identify source pages or paths supporting the answer when available.
- If the evidence is incomplete or conflicting, explain what remains uncertain
  and retrieve more information when the available tools can resolve it.
- Ask a focused question when missing context prevents meaningful progress.
- Keep the investigation within the user's request and authorized workspace.
""",
    """\
# Tool Use

- Use only the tools supplied for the current turn and their current schemas.
- When available, use `list`, `glob`, or `grep` to discover resources and `read`
  to inspect their contents. Use exact logical paths from the current context.
- Use `skill` to load applicable workflows and `ask_user` when a necessary
  detail cannot be established from the available information.
- Respect the readable roots and relative path starting point in Workspace.
- When business records are needed and `query_business_data` is available,
  read the Wiki's table dictionary and use its data_source_tag. Follow the
  tool's current available tags and named SQL parameter schema; never guess
  a tag or substitute another source after a failed query.
- Do not attempt file mutations, shell execution, or access outside the mounts.
- Independent read operations may run in parallel when supported.
- A failed lookup is not a verified conclusion. Assess the failure and choose
  a valid next step.
""",
    """\
# Tone and Style

- Lead with the answer or the next useful action.
- Explain the evidence and reasoning needed to understand the result.
- Use concise paragraphs or lists, keep uncertainty explicit, and avoid filler.
- Do not use emojis unless the user requests them.
""",
    """\
# Session-specific Guidance

## Skills
- Use only Skill names supplied by the available-Skill context.
- When a listed Skill clearly matches the task, load it before giving a
  substantive answer unless its instructions are already loaded, then follow them.
- A <command-name>...</command-name> tag indicates that the user's selected
  Skill is already loaded; do not load it again for that invocation.

## Scenes
- A Scene is a knowledge context and Wiki entry path, with an optional bound Skill.
- Use the user's explicit selection for relevant requests and follow-ups until
  the user or host updates it.
- When applying a Scene with a bound Skill, load that Skill if its instructions
  are not already loaded, then follow them from the Scene's entry path.
- When no Skill is bound, discover and read relevant pages from that entry path.
- Do not discover or switch Scenes autonomously. Do not force an unrelated
  request into the selected Scene; clarify when the task needs a selection.
- Without an explicit selection, use a relevant default Scene only if the host
  supplies one. Do not invent a default or silently replace the user's selection.
- One unsuccessful lookup does not prove that the information is absent or
  the Scene is irrelevant.
""",
)
ZHIZHI_MEMORY_INTRODUCTION = """\
# Memory

The host supplied the following persistent context and preferences.
"""


def build_zhizhi_prompt_profile(
    *,
    bot_md: str = "",
    user_md: str = "",
) -> PromptProfile | None:
    """Project 致知's Bot.md/User.md records into neutral prompt sections."""

    bot_md = bot_md.strip()
    user_md = user_md.strip()
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
    """Return the stable, subscriber-specific Wiki assistant prompt prefix."""

    return "\n\n---\n\n".join(_static_sections(assistant_name))


def build_zhizhi_system_prompt(
    *,
    profile: PromptProfile | None = None,
    workspace: WorkspacePromptContext | None = None,
    extra_dynamic_sections: Mapping[str, str] | Sequence[str] | None = None,
    assistant_name: str = ZHIZHI_ASSISTANT_NAME,
) -> SystemPrompt:
    """Compose Wiki rules with actual host context, keeping memory last."""

    if workspace is not None and not (
        workspace.readable_roots
        or workspace.writable_roots
        or workspace.relative_path_root.strip()
        or workspace.relative_path_description.strip()
        or any(rule.strip() for rule in workspace.rules)
    ):
        workspace = None
    sections = list(
        extra_dynamic_sections.values()
        if isinstance(extra_dynamic_sections, Mapping)
        else extra_dynamic_sections or ()
    )
    if profile is not None:
        sections.extend(profile.sections)
    assembled = build_system_prompt(
        workspace=workspace,
        extra_dynamic_sections=sections,
        dynamic_boundary=ZHIZHI_DYNAMIC_BOUNDARY,
    )
    static_sections = _static_sections(assistant_name)
    dynamic_sections = tuple(
        section.strip() for section in assembled.dynamic_sections if section.strip()
    )
    return SystemPrompt(
        static_sections=static_sections,
        dynamic_sections=dynamic_sections,
        full="\n\n---\n\n".join((*static_sections, *dynamic_sections)),
    )


def _static_sections(assistant_name: str) -> tuple[str, ...]:
    resolved_name = _resolve_zhizhi_assistant_name(assistant_name)
    return tuple(
        section.replace("{assistant_name}", resolved_name).strip()
        for section in ZHIZHI_STATIC_SECTIONS
    )


def _resolve_zhizhi_assistant_name(value: str) -> str:
    return value.strip() or ZHIZHI_ASSISTANT_NAME
