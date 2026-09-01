"""Transport-neutral Agent workbench commands."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_CONTENT_BYTES = 64 * 1024 - 1
MAX_METADATA_BYTES = 16 * 1024
MAX_ATTACHMENT_IDS = 16


class SlashTarget(BaseModel):
    """One explicitly selected Scene or Skill."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["scene", "skill"]
    asset_key: str = Field(min_length=1, max_length=255)
    name: str = Field(default="", max_length=255)


class AgentContext(BaseModel):
    """Trusted caller identity and active organization selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=255)
    tenant_id: str = Field(min_length=1, max_length=64)
    active_organization_unit_id: str = Field(default="", max_length=64)
    principal_id: str = Field(min_length=1, max_length=128)
    principal_type: str = Field(default="user", min_length=1, max_length=32)
    slash_target: SlashTarget | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "conversation_id",
        "tenant_id",
        "active_organization_unit_id",
        "principal_id",
        "principal_type",
    )
    @classmethod
    def strip_strings(cls, value: str) -> str:
        return value.strip()


class AgentTurnCommand(AgentContext):
    """Trusted zhizhi input for one Agent turn."""

    content: str = ""
    attachment_ids: tuple[str, ...] = ()
    request_id: str = Field(min_length=1, max_length=64)
    slash_target: SlashTarget | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id")
    @classmethod
    def strip_request_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("content")
    @classmethod
    def validate_content_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise ValueError("content is too large")
        return value

    @field_validator("attachment_ids")
    @classmethod
    def validate_attachment_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > MAX_ATTACHMENT_IDS:
            raise ValueError(f"at most {MAX_ATTACHMENT_IDS} attachments are allowed")
        if len(set(value)) != len(value):
            raise ValueError("attachment_ids must be unique")
        if any(not attachment_id.strip() or len(attachment_id) > 64 for attachment_id in value):
            raise ValueError("attachment_ids contain an invalid identifier")
        return tuple(attachment_id.strip() for attachment_id in value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_METADATA_BYTES:
            raise ValueError("metadata is too large")
        return value

    @model_validator(mode="after")
    def validate_turn(self) -> AgentTurnCommand:
        if not self.content.strip() and not self.attachment_ids and self.slash_target is None:
            raise ValueError("content, attachment_ids or slash_target is required")
        return self


class AgentUploadAttachmentCommand(AgentContext):
    """One image uploaded before the corresponding Agent turn starts."""

    request_id: str = Field(min_length=1, max_length=64)
    data: bytes

    @field_validator("request_id")
    @classmethod
    def strip_upload_request_id(cls, value: str) -> str:
        return value.strip()


class AskAnswerCommand(AgentContext):
    """Resume one suspended ask_user call."""

    request_id: str = Field(min_length=1, max_length=64)
    ask_id: str = Field(min_length=1, max_length=128)
    status: Literal["answered", "skipped"] = "answered"
    answers: dict[str, str | list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id", "ask_id")
    @classmethod
    def strip_answer_ids(cls, value: str) -> str:
        return value.strip()

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_METADATA_BYTES:
            raise ValueError("metadata is too large")
        return value
