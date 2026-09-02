"""Tenant, organization-unit, group, and principal persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gewu_core.database import TimezoneAwareDateTime, db_now
from gewu_core.ids import new_entity_id
from zhizhi_platform.database import ZhizhiBase


class TenantModel(ZhizhiBase):
    __tablename__ = "zhizhi_tenant"
    __table_args__ = (
        UniqueConstraint("normalized_tenant_code", name="uk_tenant_normalized_code"),
        UniqueConstraint("storage_key", name="uk_tenant_storage_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_code: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_tenant_code: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    tenant_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class OrganizationUnitModel(ZhizhiBase):
    __tablename__ = "zhizhi_organization_unit"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "normalized_external_key", name="uk_org_unit_tenant_external_key"
        ),
        UniqueConstraint("tenant_id", "storage_key", name="uk_org_unit_tenant_storage_key"),
        Index("idx_org_unit_parent", "tenant_id", "parent_id", "status", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_tenant.id"), nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("zhizhi_organization_unit.id"), nullable=True
    )
    external_key: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_external_key: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    unit_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class OrganizationGroupModel(ZhizhiBase):
    __tablename__ = "zhizhi_organization_group"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_key", name="uk_org_group_tenant_external_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_tenant.id"), nullable=False
    )
    external_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class PrincipalModel(ZhizhiBase):
    __tablename__ = "zhizhi_principal"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "external_principal_id", name="uk_principal_tenant_external_id"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_tenant.id"), nullable=False
    )
    external_principal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class PrincipalOrganizationUnitModel(ZhizhiBase):
    __tablename__ = "zhizhi_principal_organization_unit"
    __table_args__ = (
        UniqueConstraint(
            "principal_id", "organization_unit_id", name="uk_principal_organization_unit"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    principal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_principal.id"), nullable=False
    )
    organization_unit_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_organization_unit.id"), nullable=False
    )


class PrincipalOrganizationGroupModel(ZhizhiBase):
    __tablename__ = "zhizhi_principal_organization_group"
    __table_args__ = (
        UniqueConstraint(
            "principal_id", "organization_group_id", name="uk_principal_organization_group"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    principal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_principal.id"), nullable=False
    )
    organization_group_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_organization_group.id"), nullable=False
    )
