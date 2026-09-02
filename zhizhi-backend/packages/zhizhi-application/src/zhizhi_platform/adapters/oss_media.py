"""S3/MinIO-compatible 致知 Chat media storage."""

from __future__ import annotations

import os
from collections.abc import Callable
from io import BytesIO
from urllib.parse import urlparse

import certifi
import urllib3
from minio import Minio
from urllib3.util import Retry, Timeout

from gewu_core.blocking import run_external_task


class OssZhizhiChatMediaStore:
    """Store opaque 致知 Chat media keys in one object-storage bucket."""

    storage_backend = "oss"

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "",
        max_connections: int = 10,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 30.0,
        client_factory: Callable[..., Minio] = Minio,
    ) -> None:
        endpoint_host, secure = _parse_oss_endpoint(endpoint)
        self.bucket = bucket
        self.http_client = urllib3.PoolManager(
            timeout=Timeout(
                connect=connect_timeout_seconds,
                read=read_timeout_seconds,
            ),
            maxsize=max_connections,
            block=True,
            cert_reqs="CERT_REQUIRED",
            ca_certs=os.environ.get("SSL_CERT_FILE") or certifi.where(),
            retries=Retry(
                total=5,
                backoff_factor=0.2,
                status_forcelist=(500, 502, 503, 504),
            ),
        )
        self.client = client_factory(
            endpoint_host,
            access_key=access_key,
            secret_key=secret_key,
            region=region or None,
            secure=secure,
            http_client=self.http_client,
        )

    async def save(self, resource_key: str, data: bytes, mime_type: str) -> None:
        await run_external_task(
            self._put_object,
            resource_key,
            data,
            mime_type,
            wait_on_cancel=True,
        )

    async def read(self, resource_key: str) -> bytes:
        return await run_external_task(self._get_object, resource_key)

    async def delete(self, resource_key: str) -> None:
        await run_external_task(
            self.client.remove_object,
            self.bucket,
            resource_key,
            wait_on_cancel=True,
        )

    async def close(self) -> None:
        """Close persistent object-storage HTTP connections."""

        await run_external_task(self.http_client.clear, wait_on_cancel=True)

    def _put_object(self, resource_key: str, data: bytes, mime_type: str) -> None:
        self.client.put_object(
            self.bucket,
            resource_key,
            BytesIO(data),
            length=len(data),
            content_type=mime_type,
        )

    def _get_object(self, resource_key: str) -> bytes:
        response = self.client.get_object(self.bucket, resource_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


def _parse_oss_endpoint(endpoint: str) -> tuple[str, bool]:
    parsed = urlparse(endpoint)
    if parsed.scheme:
        return parsed.netloc or parsed.path, parsed.scheme == "https"
    return endpoint, True
