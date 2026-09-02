"""致知 Data Source source, binding, and entitlement rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gewu_core.database import TimezoneAwareDateTime, db_now
from gewu_core.ids import new_entity_id
from zhizhi_platform.database import ZhizhiBase


class DataSourceSourceModel(ZhizhiBase):
    """Admin-managed Data Source gateway source row."""

    __tablename__ = "zhizhi_data_source_source"
    __table_args__ = (UniqueConstraint("source_key", name="uk_data_source_source_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    api_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    app_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    credentials_ciphertext: Mapped[str] = mapped_column(Text, nullable=False, default="")
    credential_status: Mapped[str] = mapped_column(String(16), nullable=False, default="missing")
    default_database_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    exec_sources_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    default_max_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    hard_max_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    allow_databases: Mapped[str] = mapped_column(Text, nullable=False, default="")
    log_sql: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class DataSourceSourceBindingModel(ZhizhiBase):
    """Tenant or organization-unit source binding row."""

    __tablename__ = "zhizhi_data_source_source_binding"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scope_type",
            "organization_unit_id",
            name="uk_data_source_binding_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    organization_unit_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    data_source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class DataSourceSourceEntitlementModel(ZhizhiBase):
    """致知 scope source-pool entitlement row."""

    __tablename__ = "zhizhi_data_source_source_entitlement"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scope_type",
            "organization_unit_id",
            "data_source_id",
            name="uk_data_source_entitlement_scope_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    organization_unit_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    data_source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )
