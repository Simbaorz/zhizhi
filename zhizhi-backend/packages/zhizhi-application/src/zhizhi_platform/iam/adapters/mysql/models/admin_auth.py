"""Admin identity and RBAC rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gewu_core.database import TimezoneAwareDateTime, db_now
from gewu_core.ids import new_entity_id
from zhizhi_platform.database import ZhizhiBase


class AdminUserModel(ZhizhiBase):
    __tablename__ = "zhizhi_admin_user"
    __table_args__ = (
        UniqueConstraint("normalized_username", name="uk_admin_user_normalized_username"),
        UniqueConstraint("phone", name="uk_admin_user_phone"),
        UniqueConstraint("email", name="uk_admin_user_email"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_username: Mapped[str] = mapped_column(String(256), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    is_super: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_login_time: Mapped[datetime | None] = mapped_column(TimezoneAwareDateTime(), nullable=True)
    created_tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_source: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    created_by_admin_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by_admin_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class AdminRoleModel(ZhizhiBase):
    __tablename__ = "zhizhi_admin_role"
    __table_args__ = (UniqueConstraint("role_code", name="uk_admin_role_code"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    role_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    is_delegable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class AdminPermissionModel(ZhizhiBase):
    __tablename__ = "zhizhi_admin_permission"
    __table_args__ = (UniqueConstraint("permission_code", name="uk_admin_permission_code"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    permission_code: Mapped[str] = mapped_column(String(64), nullable=False)
    permission_name: Mapped[str] = mapped_column(String(128), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class AdminRolePermissionModel(ZhizhiBase):
    __tablename__ = "zhizhi_admin_role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uk_admin_role_permission"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    role_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_admin_role.id"), nullable=False
    )
    permission_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_admin_permission.id"), nullable=False
    )
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class AdminTenantMemberModel(ZhizhiBase):
    __tablename__ = "zhizhi_admin_tenant_member"
    __table_args__ = (
        UniqueConstraint("admin_user_id", "tenant_id", name="uk_admin_tenant_member"),
        Index("idx_admin_tenant_member_tenant", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    admin_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_admin_user.id"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    scope_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="tenant")
    created_by_admin_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("zhizhi_admin_user.id"), nullable=True
    )
    updated_by_admin_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("zhizhi_admin_user.id"), nullable=True
    )
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class AdminTenantRoleModel(ZhizhiBase):
    __tablename__ = "zhizhi_admin_tenant_role"
    __table_args__ = (UniqueConstraint("tenant_member_id", "role_id", name="uk_admin_tenant_role"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_member_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_admin_tenant_member.id"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_admin_role.id"), nullable=False
    )
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )


class AdminTenantScopeModel(ZhizhiBase):
    __tablename__ = "zhizhi_admin_tenant_scope"
    __table_args__ = (
        UniqueConstraint(
            "tenant_member_id",
            "scope_type",
            "scope_organization_unit_id",
            name="uk_admin_tenant_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_entity_id)
    tenant_member_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("zhizhi_admin_tenant_member.id"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_organization_unit_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    create_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now
    )
    update_time: Mapped[datetime] = mapped_column(
        TimezoneAwareDateTime(), nullable=False, default=db_now, onupdate=db_now
    )
