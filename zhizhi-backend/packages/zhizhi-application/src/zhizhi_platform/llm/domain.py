"""致知-managed LLM provider constants and persistence-neutral models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMProvider(StrEnum):
    """Model providers supported by the current 致知 subscriber."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class ModelProtocol(StrEnum):
    """Message protocol used by one managed provider."""

    OPENAI_CHAT = "openai-chat"
    ANTHROPIC_MESSAGES = "anthropic-messages"


class ManagedLLMConfig(BaseModel):
    """Admin-managed model provider configuration."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    alias: str
    display_name: str = ""
    provider: str
    protocol: str
    model_name: str
    endpoint_url: str = ""
    status: str = "active"
    support_stream: bool = True
    support_tools: bool = True
    support_vision: bool = False
    support_thinking: bool = False
    timeout_seconds: int = 600
    generation_config: dict[str, Any] = Field(default_factory=dict)
    provider_config: dict[str, Any] = Field(default_factory=dict)
    credentials_ciphertext: str = ""
    credential_status: str = "missing"
    last_test_status: str = "untested"
    last_test_message: str = ""
    last_test_time: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ManagedLLMBinding(BaseModel):
    """Model selected for one tenant or organization-unit scope."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_id: str = Field(min_length=1)
    scope_type: str
    organization_unit_id: str = ""
    llm_config_id: str
    status: str = "active"
    runtime_overrides: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ManagedLLMEntitlement(BaseModel):
    """Model made available to one tenant or organization-unit scope."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_id: str = Field(min_length=1)
    scope_type: str
    organization_unit_id: str = ""
    llm_config_id: str
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None
