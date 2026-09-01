"""Stable Runtime event encoding for the Agent workbench SSE endpoint."""

from __future__ import annotations

import json

from pydantic import BaseModel

from gewu_agent_runtime.compaction import FullCompactProgress
from gewu_agent_runtime.runtime import RuntimeEvent


def encode_sse_event(
    event: RuntimeEvent,
    *,
    run_id: str,
    request_id: str,
    conversation_id: str,
) -> str:
    event_name = "memory_compaction" if isinstance(event, FullCompactProgress) else str(event.type)
    payload = _event_payload(event)
    payload.update(
        {
            "run_id": run_id,
            "request_id": request_id,
            "conversation_id": conversation_id,
        }
    )
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def encode_stream_end(*, run_id: str, request_id: str, conversation_id: str) -> str:
    payload = {
        "run_id": run_id,
        "request_id": request_id,
        "conversation_id": conversation_id,
    }
    return f"event: done\ndata: {json.dumps(payload)}\n\n"


def encode_stream_error(
    *,
    code: str,
    message: str,
    run_id: str,
    request_id: str,
    conversation_id: str,
) -> str:
    payload = {
        "code": code,
        "message": message,
        "run_id": run_id,
        "request_id": request_id,
        "conversation_id": conversation_id,
    }
    return f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _event_payload(event: BaseModel) -> dict[str, object]:
    return event.model_dump(mode="json")
