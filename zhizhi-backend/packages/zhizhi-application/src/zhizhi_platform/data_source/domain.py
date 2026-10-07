"""Data-source configuration, grants, and multi-source selections."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DataSourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = ""
    source_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    tag: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z][A-Z0-9_-]*$")
    display_name: str = Field(default="", max_length=128)
    description: str = Field(default="", max_length=512)
    driver: Literal["mysql", "postgresql"] = "mysql"
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=3306, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    credentials_ciphertext: str = Field(default="", repr=False)
    server_id: str = Field(default="main", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    endpoint_url: str = "http://127.0.0.1:8002/mcp"
    status: Literal["active", "inactive"] = "active"
    connection_revision: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    pool_size: int = Field(default=3, ge=1, le=32)
    pool_timeout_seconds: float = Field(default=5, gt=0, le=60)
    connect_timeout_seconds: float = Field(default=5, gt=0, le=60)
    query_timeout_seconds: float = Field(default=30, gt=0, le=300)
    max_rows: int = Field(default=500, ge=1, le=10000)
    max_result_bytes: int = Field(default=262144, ge=2048, le=1048576)
    allowed_schemas: tuple[str, ...] = ()
    tls: bool = False
    last_test_status: str = "untested"

    @field_validator("tag", mode="before")
    @classmethod
    def normalize_tag(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("endpoint_url")
    @classmethod
    def require_http_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "MCP endpoint must be an HTTP(S) URL without embedded credentials, query, or fragment."
            )
        return value.rstrip("/")

    def public(self, *, detailed: bool = False) -> dict[str, object]:
        if detailed:
            result = self.model_dump(mode="json", exclude={"credentials_ciphertext"})
        else:
            result = self.model_dump(
                mode="json",
                include={
                    "id",
                    "source_key",
                    "tag",
                    "display_name",
                    "description",
                    "driver",
                    "status",
                    "max_rows",
                    "last_test_status",
                },
            )
        result["has_credentials"] = bool(self.credentials_ciphertext)
        return result


class SourceEntitlement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = ""
    tenant_id: str = Field(min_length=1)
    organization_unit_id: str = ""
    source_id: str = Field(min_length=1)


class SourceBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = ""
    tenant_id: str = Field(min_length=1)
    organization_unit_id: str = ""
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    default_source_id: str = Field(min_length=1)
    status: Literal["active", "inactive"] = "active"

    @model_validator(mode="after")
    def validate_selection(self) -> SourceBinding:
        if (
            len(set(self.source_ids)) != len(self.source_ids)
            or self.default_source_id not in self.source_ids
        ):
            raise ValueError("Bound sources must be unique and include the default source.")
        return self


class SourceSelection(BaseModel):
    model_config = ConfigDict(frozen=True)
    sources: tuple[DataSourceConfig, ...]
    default_tag: str
