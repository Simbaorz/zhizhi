import json

from gewu_agent_runtime.engine import AssistantDelta
from zhizhi_web_api.sse import encode_sse_event, encode_stream_end, encode_stream_error


def test_sse_event_includes_runtime_correlation_ids() -> None:
    encoded = encode_sse_event(
        AssistantDelta(message_id="m1", content="你好"),
        run_id="r1",
        request_id="req1",
        conversation_id="c1",
    )

    lines = encoded.strip().splitlines()
    assert lines[0] == "event: assistant_delta"
    assert json.loads(lines[1].removeprefix("data: ")) == {
        "type": "assistant_delta",
        "message_id": "m1",
        "content": "你好",
        "run_id": "r1",
        "request_id": "req1",
        "conversation_id": "c1",
    }


def test_stream_end_is_explicit() -> None:
    encoded = encode_stream_end(run_id="r1", request_id="req1", conversation_id="c1")
    assert encoded.startswith("event: done\n")


def test_stream_error_contains_stable_correlation_fields() -> None:
    encoded = encode_stream_error(
        code="model_not_configured",
        message="No model is configured.",
        run_id="r1",
        request_id="req1",
        conversation_id="c1",
    )

    assert encoded.startswith("event: error\n")
    assert '"code": "model_not_configured"' in encoded
    assert '"run_id": "r1"' in encoded
