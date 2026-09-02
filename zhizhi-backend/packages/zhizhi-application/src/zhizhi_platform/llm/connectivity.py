"""Provider-specific connectivity tests for 致知 model administration."""

from __future__ import annotations

from typing import Any

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from zhizhi_platform.llm.domain import LLMProvider
from zhizhi_platform.llm.ports import (
    LLMConnectivityNetworkError,
    LLMConnectivityRequest,
    LLMConnectivityResult,
    LLMConnectivityTimeoutError,
)


class ProviderConnectivityTester:
    """Run administrative connectivity tests against supported providers."""

    def __init__(
        self,
        *,
        connect_timeout_seconds: float = 5.0,
        pool_timeout_seconds: float = 5.0,
    ) -> None:
        self._connect_timeout_seconds = connect_timeout_seconds
        self._pool_timeout_seconds = pool_timeout_seconds

    async def test(self, request: LLMConnectivityRequest) -> LLMConnectivityResult:
        try:
            if request.provider == LLMProvider.OPENAI.value:
                return await _test_openai(
                    request,
                    connect_timeout_seconds=self._connect_timeout_seconds,
                    pool_timeout_seconds=self._pool_timeout_seconds,
                )
            if request.provider == LLMProvider.ANTHROPIC.value:
                return await _test_anthropic(
                    request,
                    connect_timeout_seconds=self._connect_timeout_seconds,
                    pool_timeout_seconds=self._pool_timeout_seconds,
                )
            raise ValueError("Unsupported model provider.")
        except httpx.TimeoutException as exc:
            raise LLMConnectivityTimeoutError from exc
        except httpx.NetworkError as exc:
            raise LLMConnectivityNetworkError from exc


async def _test_openai(
    request: LLMConnectivityRequest,
    *,
    connect_timeout_seconds: float,
    pool_timeout_seconds: float,
) -> LLMConnectivityResult:
    client = AsyncOpenAI(
        api_key=_credential_api_key(request.credentials) or "none",
        base_url=request.endpoint_url or None,
        timeout=_request_timeout(
            request.timeout_seconds,
            connect_seconds=connect_timeout_seconds,
            pool_seconds=pool_timeout_seconds,
        ),
    )
    messages: list[dict[str, str]] = []
    if request.system_prompt.strip():
        messages.append({"role": "system", "content": request.system_prompt.strip()})
    messages.append({"role": "user", "content": request.prompt})
    request_kwargs: dict[str, Any] = {
        "model": request.model_name,
        "messages": messages,
        "stream": False,
        **_openai_generation_kwargs(request.generation_config),
    }
    try:
        response: Any = await client.chat.completions.create(**request_kwargs)
    finally:
        await client.close()
    choice = response.choices[0] if response.choices else None
    usage = response.usage
    return LLMConnectivityResult(
        content=choice.message.content if choice and choice.message.content else "",
        usage=(
            _usage_dict(
                input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
            )
            if usage
            else None
        ),
    )


async def _test_anthropic(
    request: LLMConnectivityRequest,
    *,
    connect_timeout_seconds: float,
    pool_timeout_seconds: float,
) -> LLMConnectivityResult:
    client = AsyncAnthropic(
        api_key=_credential_api_key(request.credentials),
        base_url=request.endpoint_url or None,
        timeout=_request_timeout(
            request.timeout_seconds,
            connect_seconds=connect_timeout_seconds,
            pool_seconds=pool_timeout_seconds,
        ),
    )
    kwargs: dict[str, Any] = {
        "model": request.model_name,
        "messages": [{"role": "user", "content": request.prompt}],
        "max_tokens": int(request.generation_config.get("max_tokens") or 1024),
    }
    if request.system_prompt.strip():
        kwargs["system"] = request.system_prompt.strip()
    if "temperature" in request.generation_config:
        kwargs["temperature"] = request.generation_config["temperature"]
    if "top_p" in request.generation_config:
        kwargs["top_p"] = request.generation_config["top_p"]
    try:
        response = await client.messages.create(**kwargs)
    finally:
        await client.close()
    content = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    usage = response.usage
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    return LLMConnectivityResult(
        content=content,
        usage=_usage_dict(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
    )


def _openai_generation_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "temperature",
        "top_p",
        "max_tokens",
        "presence_penalty",
        "frequency_penalty",
        "seed",
    }
    return {key: value for key, value in config.items() if key in allowed and value is not None}


def _credential_api_key(credentials: dict[str, Any]) -> str:
    return _string_value(credentials.get("api_key"))


def _string_value(value: Any) -> str:
    return str(value or "").strip()


def _usage_dict(*, input_tokens: int, output_tokens: int, total_tokens: int) -> dict[str, int]:
    return {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(total_tokens or input_tokens + output_tokens),
    }


def _request_timeout(
    read_seconds: float,
    *,
    connect_seconds: float,
    pool_seconds: float,
) -> httpx.Timeout:
    return httpx.Timeout(
        timeout=read_seconds,
        connect=connect_seconds,
        pool=pool_seconds,
    )
