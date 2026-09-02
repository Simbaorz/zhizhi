"""致知 model configuration decryption and provider capability construction."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from gewu_agent_runtime.llm import ChatModel, Message, ModelRuntimeConfig, ModelStreamChunk
from gewu_agent_runtime.tools import Tool
from zhizhi_platform.llm.ports import LLMCredentialCipher
from zhizhi_platform.llm.resolution import (
    ACTIVE_STATUS,
    ZhizhiModelBindingRecord,
)
from zhizhi_platform.runtime_contracts import ZhizhiResolvedModel

CONFIGURED_CREDENTIAL_STATUS = "configured"
DEFAULT_CONTEXT_WINDOW = 32_768
MAX_SUMMARY_OUTPUT_TOKENS = 8_192
MIN_SUMMARY_OUTPUT_TOKENS = 1_024


class ZhizhiModelConfigRecord(BaseModel):
    """致知-managed provider configuration required for a runtime model."""

    model_config = ConfigDict(frozen=True)

    config_id: str = Field(min_length=1)
    alias: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    protocol: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    endpoint_url: str = ""
    status: str = ACTIVE_STATUS
    support_stream: bool = True
    support_tools: bool = True
    support_vision: bool = False
    timeout_seconds: int = 600
    generation_config: dict[str, Any] = Field(default_factory=dict)
    provider_config: dict[str, Any] = Field(default_factory=dict)
    credentials_ciphertext: str = ""
    credential_status: str = "missing"


class ZhizhiModelConfigRepository(Protocol):
    """Load one provider configuration referenced by an authorized binding."""

    async def get_config(self, config_id: str) -> ZhizhiModelConfigRecord | None:
        """Return one model configuration by ID."""


class ProviderChatModelFactory(Protocol):
    """Create a provider-specific client without selecting business authorization."""

    def create(self, config: ModelRuntimeConfig) -> ChatModel:
        """Return a model client for one already-resolved configuration."""


class ZhizhiModelCapabilityBuilder:
    """Build main and no-tools compaction models for one authorized binding."""

    def __init__(
        self,
        repository: ZhizhiModelConfigRepository,
        factory: ProviderChatModelFactory,
        cipher: LLMCredentialCipher,
    ) -> None:
        self._repository = repository
        self._factory = factory
        self._cipher = cipher

    async def create(
        self,
        binding: ZhizhiModelBindingRecord,
    ) -> ZhizhiResolvedModel | None:
        config = await self._repository.get_config(binding.model_config_id)
        if config is None or config.status != ACTIVE_STATUS:
            return None
        if config.credential_status != CONFIGURED_CREDENTIAL_STATUS:
            return None
        credentials = self._cipher.decrypt(config.credentials_ciphertext)
        runtime_config = _runtime_config(config, binding, credentials)
        main_model = self._factory.create(runtime_config)

        max_output_tokens = min(
            MAX_SUMMARY_OUTPUT_TOKENS,
            max(MIN_SUMMARY_OUTPUT_TOKENS, runtime_config.context_window // 10),
        )
        summary_generation = dict(runtime_config.generation_config)
        summary_generation["max_tokens"] = max_output_tokens
        summary_client = self._factory.create(
            runtime_config.model_copy(
                update={
                    "support_tools": False,
                    "generation_config": summary_generation,
                }
            )
        )
        return ZhizhiResolvedModel(
            model=main_model,
            compaction_model=BoundCompactionModel(
                client=summary_client,
                model_ref=runtime_config.model_ref,
                model_name=runtime_config.model_name,
                context_window=runtime_config.context_window,
                max_output_tokens=max_output_tokens,
            ),
        )


class BoundCompactionModel:
    """Expose a provider client as the Runtime's bounded no-tools model."""

    def __init__(
        self,
        *,
        client: ChatModel,
        model_ref: str,
        model_name: str,
        context_window: int,
        max_output_tokens: int,
    ) -> None:
        self._client = client
        self.model_ref = model_ref
        self.model_name = model_name
        self.context_window = context_window
        self.max_output_tokens = max_output_tokens

    def stream_chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[Tool],
    ) -> AsyncIterator[ModelStreamChunk]:
        return self._client.stream_chat(messages, tools)


def _runtime_config(
    config: ZhizhiModelConfigRecord,
    binding: ZhizhiModelBindingRecord,
    credentials: dict[str, Any],
) -> ModelRuntimeConfig:
    generation_config = dict(config.generation_config)
    generation_config.update(binding.runtime_overrides)
    return ModelRuntimeConfig(
        model_ref=config.config_id,
        provider=config.provider,
        protocol=config.protocol,
        model_name=config.model_name,
        endpoint_url=config.endpoint_url,
        api_key=str(credentials.get("api_key") or ""),
        timeout_seconds=config.timeout_seconds,
        support_stream=config.support_stream,
        support_tools=config.support_tools,
        support_vision=config.support_vision,
        context_window=int(config.provider_config.get("context_window") or DEFAULT_CONTEXT_WINDOW),
        generation_config=generation_config,
        provider_config=dict(config.provider_config),
        credentials=dict(credentials),
    )
