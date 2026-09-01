from __future__ import annotations

import pytest
from pydantic import ValidationError

from zhizhi import AgentTurnCommand, runtime_conversation_id


def _command(**updates: object) -> AgentTurnCommand:
    values: dict[str, object] = {
        "conversation_id": "conversation-1",
        "content": "question",
        "request_id": "request-1",
        "tenant_id": "tenant-1",
        "active_organization_unit_id": "team-1",
        "principal_id": "user-1",
        "principal_type": "user",
        "metadata": {},
    }
    values.update(updates)
    return AgentTurnCommand.model_validate(values)


def test_command_uses_flattened_zhizhi_contract() -> None:
    command = _command()

    assert command.conversation_id == "conversation-1"
    assert command.tenant_id == "tenant-1"
    assert command.active_organization_unit_id == "team-1"
    assert command.principal_id == "user-1"


def test_command_rejects_legacy_or_untrusted_identity_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _command(role="admin")


def test_command_keeps_bounded_turn_metadata() -> None:
    assert _command(metadata={"source": "online"}).metadata == {"source": "online"}
    with pytest.raises(ValidationError, match="metadata is too large"):
        _command(metadata={"value": "x" * (16 * 1024)})


def test_command_accepts_images_without_text() -> None:
    command = _command(content="", attachment_ids=["image-1", "image-2"])

    assert command.attachment_ids == ("image-1", "image-2")


def test_command_rejects_duplicate_or_excessive_images() -> None:
    with pytest.raises(ValidationError, match="attachment_ids must be unique"):
        _command(attachment_ids=["image-1", "image-1"])
    with pytest.raises(ValidationError, match="at most 16 attachments"):
        _command(attachment_ids=[f"image-{index}" for index in range(17)])


def test_runtime_conversation_id_is_stable_for_conversation_and_principal() -> None:
    first = runtime_conversation_id("online", "conversation-1", "user-1")

    assert first == runtime_conversation_id("online", "conversation-1", "user-1")
    assert first != runtime_conversation_id("online", "conversation-1", "user-2")
    assert first != runtime_conversation_id("online", "conversation-2", "user-1")
    assert len(first) == 64
