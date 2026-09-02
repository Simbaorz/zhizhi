"""致知-gated prompt trace debug file writer."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

from gewu_agent_runtime.llm import ModelTracePayload, ModelTraceSink
from gewu_core.file_tasks import FileTaskLane, run_file_mutation
from zhizhi_platform.iam.identity import AccessScope

logger = logging.getLogger(__name__)


class ZhizhiPromptTraceController:
    """Apply the explicit 致知 actor policy before creating a trace sink."""

    def __init__(
        self,
        project_home: str | Path,
        *,
        enabled: bool = False,
        tenant_id: str = "",
        user_id: str = "",
    ) -> None:
        self._project_home = Path(project_home).expanduser()
        self._enabled = enabled
        self._tenant_id = tenant_id
        self._user_id = user_id

    async def start_turn(self, scope: AccessScope) -> ModelTraceSink | None:
        """Create a trace sink only for the configured 致知 actor."""

        if not self._enabled_for(scope):
            return None
        trace_dir = self._project_home / "debug" / "trace_prompt"
        await run_file_mutation(
            self._clear_markdown,
            trace_dir,
            lane=FileTaskLane.INTERACTIVE,
        )
        return PromptTraceTurn(trace_dir)

    def _enabled_for(self, scope: AccessScope) -> bool:
        return (
            self._enabled
            and bool(self._tenant_id)
            and bool(self._user_id)
            and self._tenant_id == scope.tenant_id
            and self._user_id == scope.principal_id
        )

    @staticmethod
    def _clear_markdown(trace_dir: Path) -> None:
        try:
            trace_dir.mkdir(parents=True, exist_ok=True)
            for path in trace_dir.glob("*.md"):
                if path.is_file():
                    path.unlink()
        except OSError as exc:
            logger.warning(
                "Failed to clear prompt trace directory: %s exception_type=%s",
                trace_dir,
                type(exc).__name__,
            )


class PromptTraceTurn:
    """Write numbered 致知-compatible trace files for one Runtime turn."""

    def __init__(self, trace_dir: Path) -> None:
        self.trace_dir = trace_dir
        self._index = 0

    async def write(self, payload: ModelTracePayload) -> None:
        self._index += 1
        path = self.trace_dir / f"{self._index}.md"
        await run_file_mutation(
            self._write_payload,
            path,
            payload,
            lane=FileTaskLane.INTERACTIVE,
        )

    def _write_payload(self, path: Path, payload: ModelTracePayload) -> None:
        try:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(format_trace_payload(payload), encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "Failed to write prompt trace file: %s exception_type=%s",
                path,
                type(exc).__name__,
            )


def format_trace_payload(payload: ModelTracePayload) -> str:
    """Format one redacted provider request payload exactly as 致知 does."""

    request = _redact_trace_value(payload.request)
    lines = [f"# Prompt Trace {payload.provider}", ""]
    request_metadata = {
        key: value for key, value in request.items() if key not in {"messages", "system", "tools"}
    }
    if request_metadata:
        lines.extend(_json_section("Request", request_metadata))
    system = request.get("system")
    if system:
        lines.extend(_message_block("system", system))
    for message in request.get("messages") or []:
        if isinstance(message, dict):
            lines.extend(_provider_message(message))
    if "tools" in request:
        lines.extend(_json_section("Tools", request.get("tools") or []))
    return "\n".join(lines).rstrip() + "\n"


def _provider_message(message: dict[str, Any]) -> list[str]:
    role = str(message.get("role") or "")
    attrs: dict[str, str] = {"role": role}
    tool_call_id = message.get("tool_call_id")
    if tool_call_id:
        attrs["tool_call_id"] = str(tool_call_id)
    lines = [_opening_tag("Message", attrs)]
    if "content" in message:
        lines.extend(_content_lines(message.get("content")))
    if message.get("tool_calls"):
        lines.extend(_json_section("ToolCalls", message["tool_calls"]))
    lines.extend(("</Message>", ""))
    return lines


def _message_block(role: str, content: Any) -> list[str]:
    return [
        _opening_tag("Message", {"role": role}),
        *_content_lines(content),
        "</Message>",
        "",
    ]


def _opening_tag(name: str, attrs: dict[str, str]) -> str:
    formatted_attrs = " ".join(f"{key}={quoteattr(value)}" for key, value in attrs.items())
    return f"<{name} {formatted_attrs}>"


def _content_lines(content: Any) -> list[str]:
    if content is None:
        return [""]
    if isinstance(content, str):
        return [content]
    return _json_fence(content)


def _json_section(name: str, value: Any) -> list[str]:
    return [f"<{name}>", *_json_fence(value), f"</{name}>", ""]


def _json_fence(value: Any) -> list[str]:
    return ["```json", json.dumps(value, ensure_ascii=False, indent=2), "```"]


def _redact_trace_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {key: _redact_trace_value(item) for key, item in value.items()}
        if redacted.get("type") == "image_url":
            image_url = redacted.get("image_url")
            if isinstance(image_url, dict) and str(image_url.get("url", "")).startswith(
                "data:image/"
            ):
                image_url["url"] = _redact_data_url(str(image_url["url"]))
        if redacted.get("type") == "base64" and "data" in redacted:
            redacted["data"] = "[redacted image base64]"
        return redacted
    if isinstance(value, list):
        return [_redact_trace_value(item) for item in value]
    if isinstance(value, str) and value.startswith("data:image/"):
        return _redact_data_url(value)
    return value


def _redact_data_url(value: str) -> str:
    prefix = value.split(",", 1)[0]
    return f"{prefix},[redacted image base64]"
