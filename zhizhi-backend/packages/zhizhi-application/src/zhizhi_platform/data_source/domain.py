"""Persistence-neutral 致知 Data Source resource models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ManagedDataSourceSource(BaseModel):
    """Admin-managed Data Source gateway source."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    source_key: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    status: str = "active"
    api_url: str = ""
    app_id: str = ""
    credentials_ciphertext: str = ""
    credential_status: str = "missing"
    default_database_key: str = ""
    exec_sources_code: str = ""
    timeout_seconds: int = 30
    default_max_rows: int = 50
    hard_max_rows: int = 500
    allow_databases: str = ""
    log_sql: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ManagedDataSourceSourceBinding(BaseModel):
    """Tenant or organization-unit binding to one Data Source source."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_id: str = Field(min_length=1)
    scope_type: str
    organization_unit_id: str = ""
    data_source_id: str
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ManagedDataSourceSourceEntitlement(BaseModel):
    """Tenant or organization-unit available-source pool entry."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    tenant_id: str = Field(min_length=1)
    scope_type: str
    organization_unit_id: str = ""
    data_source_id: str
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None
