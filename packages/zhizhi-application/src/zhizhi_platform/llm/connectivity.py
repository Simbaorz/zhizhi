"""Provider-specific connectivity tests for 致知 model administration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import string
from datetime import datetime
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
            if request.provider == LLMProvider.UNICOM.value:
                return await _test_unicom(
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


async def _test_unicom(
    request: LLMConnectivityRequest,
    *,
    connect_timeout_seconds: float,
    pool_timeout_seconds: float,
) -> LLMConnectivityResult:
    body = {
        "model": request.model_name,
        "messages": _unicom_messages(
            request.prompt,
            request.system_prompt,
            request.provider_config,
        ),
        "stream": False,
        **_unicom_generation_kwargs(request.generation_config, request.provider_config),
    }
    payload = _build_unicom_payload(
        app_id=_string_value(request.credentials.get("app_id")),
        app_secret=_string_value(request.credentials.get("app_secret")),
        req_key=_unicom_req_key(request.provider_config),
        body_params=body,
    )
    headers = _unicom_headers(request.provider_config, request.credentials)
    timeout = _request_timeout(
        request.timeout_seconds,
        connect_seconds=connect_timeout_seconds,
        pool_seconds=pool_timeout_seconds,
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            request.endpoint_url,
            json=payload,
            headers=headers,
        ) as response:
            response.raise_for_status()
            raw_body = await response.aread()
    data = await asyncio.to_thread(json.loads, raw_body)
    body_data = _unwrap_unicom_body(data, request.provider_config)
    choices = body_data.get("choices", []) if isinstance(body_data, dict) else []
    content = ""
    if choices:
        message = choices[0].get("message", {})
        content = _string_value(message.get("content"))
    return LLMConnectivityResult(
        content=content,
        usage=_parse_usage(body_data.get("usage") if isinstance(body_data, dict) else None),
    )


def _unicom_messages(
    prompt: str,
    system_prompt: str,
    provider_config: dict[str, Any],
) -> list[dict[str, str]]:
    role_reflect = _role_reflect(provider_config)
    messages: list[dict[str, str]] = []
    if system_prompt.strip():
        messages.append({"role": role_reflect["system"], "content": system_prompt.strip()})
    messages.append({"role": role_reflect["user"], "content": prompt})
    return messages


def _build_unicom_payload(
    *,
    app_id: str,
    app_secret: str,
    req_key: str,
    body_params: dict[str, Any],
) -> dict[str, Any]:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S %f")[:-3]
    trans_id = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3] + "".join(
        random.choices(string.digits, k=6)
    )
    head = {"APP_ID": app_id, "TIMESTAMP": timestamp, "TRANS_ID": trans_id}
    head["TOKEN"] = _generate_unicom_token(head, app_secret)
    return {
        "UNI_BSS_HEAD": head,
        "UNI_BSS_BODY": {req_key: body_params},
        "UNI_BSS_ATTACHED": {"MEDIA_INFO": ""},
    }


def _generate_unicom_token(params: dict[str, Any], app_secret: str) -> str:
    sorted_items = sorted((key, value) for key, value in params.items() if key.upper() != "TOKEN")
    base_str = "".join(f"{key}{value}" for key, value in sorted_items) + app_secret
    return hashlib.md5(base_str.encode("utf-8")).hexdigest()


def _unwrap_unicom_body(data: dict[str, Any], provider_config: dict[str, Any]) -> dict[str, Any]:
    body = data.get("UNI_BSS_BODY")
    req_key = _unicom_req_key(provider_config)
    if isinstance(body, dict):
        nested = body.get(req_key)
        if isinstance(nested, dict):
            return nested
    return data


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


def _unicom_generation_kwargs(
    generation_config: dict[str, Any],
    provider_config: dict[str, Any],
) -> dict[str, Any]:
    kwargs = _openai_generation_kwargs(generation_config)
    kwargs["chat_template_kwargs"] = _dict_value(provider_config.get("chat_template_kwargs"))
    return kwargs


def _unicom_headers(
    provider_config: dict[str, Any],
    credentials: dict[str, Any],
) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    headers.update(_dict_string_values(provider_config.get("extra_headers")))
    authorization = _nlpt_authorization(credentials)
    if authorization:
        headers["nlpt-Authorization"] = authorization
    return headers


def _role_reflect(provider_config: dict[str, Any]) -> dict[str, str]:
    raw = _dict_value(provider_config.get("role_reflect"))
    return {
        "system": _string_value(raw.get("system")) or "system",
        "assistant": _string_value(raw.get("assistant")) or "assistant",
        "user": _string_value(raw.get("user")) or "user",
    }


def _unicom_req_key(provider_config: dict[str, Any]) -> str:
    return _string_value(provider_config.get("req_key")) or "CHAT_REQ"


def _credential_api_key(credentials: dict[str, Any]) -> str:
    return _string_value(credentials.get("api_key"))


def _nlpt_authorization(credentials: dict[str, Any]) -> str:
    return _string_value(credentials.get("nlpt_authorization") or credentials.get("authorization"))


def _string_value(value: Any) -> str:
    return str(value or "").strip()


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_string_values(value: Any) -> dict[str, str]:
    return {
        str(key): str(item)
        for key, item in _dict_value(value).items()
        if str(key).strip() and str(item).strip()
    }


def _parse_usage(usage: Any) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None
    return _usage_dict(
        input_tokens=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
    )


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
