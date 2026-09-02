"""致知 LLM configuration, binding, and entitlement rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gewu_core.database import TimezoneAwareDateTime, db_now
from gewu_core.ids import new_entity_id
from zhizhi_platform.database import ZhizhiBase


class LLMConfigModel(ZhizhiBase):
    """Admin-managed model provider configuration row."""

    __tablename__ = "zhizhi_llm_config"
    __table_args__ = (UniqueConstraint("alias", name="uk_llm_config_alias"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    protocol: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    support_stream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    support_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    support_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    support_thinking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    generation_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    provider_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    credentials_ciphertext: Mapped[str] = mapped_column(Text, nullable=False, default="")
    credential_status: Mapped[str] = mapped_column(String(16), nullable=False, default="missing")
    last_test_status: Mapped[str] = mapped_column(String(16), nullable=False, default="untested")
    last_test_message: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    last_test_time: Mapped[datetime | None] = mapped_column(TimezoneAwareDateTime(), nullable=True)
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class LLMBindingModel(ZhizhiBase):
    """Tenant or organization-unit model binding row."""

    __tablename__ = "zhizhi_llm_binding"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "scope_type", "organization_unit_id", name="uk_llm_binding_scope"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    organization_unit_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    llm_config_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    runtime_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class LLMEntitlementModel(ZhizhiBase):
    """Tenant or organization-unit available model pool row."""

    __tablename__ = "zhizhi_llm_entitlement"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scope_type",
            "organization_unit_id",
            "llm_config_id",
            name="uk_llm_entitlement_scope_model",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    organization_unit_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    llm_config_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )
