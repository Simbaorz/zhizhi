import json
from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel

from gewu_agent_runtime import ConversationMessage
from zhizhi import MessagePage
from zhizhi_web_api.error_messages import localized_error_message, localized_message_page
from zhizhi_web_api.sse import encode_sse_event


def test_history_errors_are_localized_without_mutating_runtime_storage() -> None:
    original = ConversationMessage.model_validate(
        {
            "conversation_id": "c1",
            "sequence": 1,
            "role": "assistant",
            "kind": "error",
            "content": "The model service timed out.",
            "payload": {"code": "model_timeout"},
            "created_at": datetime(2026, 1, 1),
        }
    )
    page = localized_message_page(MessagePage(conversation_id="c1", messages=(original,)))
    assert page.messages[0].content == "模型服务响应超时，请稍后重试。"
    assert page.messages[0].payload["code"] == "model_timeout"
    assert page.messages[0].created_at.tzinfo is not None
    assert original.content == "The model service timed out."


def test_live_and_history_errors_use_the_same_safe_message() -> None:
    class Error(BaseModel):
        type: str = "error"
        code: str = "model_timeout"
        message: str = "The model service timed out."

    encoded = encode_sse_event(
        cast(Any, Error()), run_id="r1", request_id="q1", conversation_id="c1"
    )
    payload = json.loads(encoded.strip().splitlines()[1].removeprefix("data: "))
    assert payload["message"] == localized_error_message("model_timeout", "")
    assert payload["code"] == "model_timeout"
    assert (
        localized_error_message("unknown", "private upstream message")
        == "智能助手执行失败，请稍后重试。"
    )
