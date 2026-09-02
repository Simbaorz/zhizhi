"""Bounded HTTP transport for the 致知 Data Source gateway."""

from __future__ import annotations

import json
from typing import Any

import httpx

from gewu_core.blocking import run_cpu_task

DEFAULT_MAX_DATA_SOURCE_RESPONSE_BYTES = 4 * 1024 * 1024
_RESPONSE_TOO_LARGE_MESSAGE = (
    "Data source query gateway response exceeds the configured byte limit."
)


class DataSourceResponseTooLargeError(RuntimeError):
    """An upstream response exceeded the configured receive capacity."""


class HttpDataSourceQueryGateway:
    """POST one query and decode only an already-bounded response body."""

    def __init__(
        self,
        *,
        max_response_bytes: int = DEFAULT_MAX_DATA_SOURCE_RESPONSE_BYTES,
        client: httpx.AsyncClient | None = None,
        connect_timeout_seconds: float = 5.0,
        pool_timeout_seconds: float = 5.0,
    ) -> None:
        if max_response_bytes < 1:
            raise ValueError("Data source response capacity must be at least 1 byte.")
        self._max_response_bytes = max_response_bytes
        self._client = client
        self._owns_client = client is None
        self._connect_timeout_seconds = connect_timeout_seconds
        self._pool_timeout_seconds = pool_timeout_seconds
        self._closed = False

    async def call(
        self,
        api_url: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> Any:
        """Call the gateway while bounding declared and received bytes."""

        client = self._get_client()
        async with client.stream(
            "POST",
            api_url,
            json=payload,
            timeout=httpx.Timeout(
                timeout=timeout_seconds,
                connect=self._connect_timeout_seconds,
                pool=self._pool_timeout_seconds,
            ),
        ) as response:
            response.raise_for_status()
            self._reject_declared_oversize(response)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > self._max_response_bytes:
                    raise DataSourceResponseTooLargeError(_RESPONSE_TOO_LARGE_MESSAGE)
                body.extend(chunk)
        return await run_cpu_task(json.loads, body)

    async def aclose(self) -> None:
        """Close an internally owned HTTP client exactly once."""

        if self._closed:
            return
        self._closed = True
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def _get_client(self) -> httpx.AsyncClient:
        if self._closed:
            raise RuntimeError("Data source HTTP gateway is closed.")
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    def _reject_declared_oversize(self, response: httpx.Response) -> None:
        content_length = response.headers.get("content-length")
        if content_length is None:
            return
        try:
            declared_bytes = int(content_length)
        except ValueError:
            return
        if declared_bytes > self._max_response_bytes:
            raise DataSourceResponseTooLargeError(_RESPONSE_TOO_LARGE_MESSAGE)
