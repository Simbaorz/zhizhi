"""Zhizhi audit identities and sanitized administrative records."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdminAuditLog(BaseModel):
    """One sanitized administrative operation audit record."""

    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    operator_admin_user_id: str | None = None
    operator_is_super: bool = False
    action: str
    target_resource_type: str
    target_resource_id: str
    target_tenant_id: str | None = None
    scope_summary: dict[str, object] = Field(default_factory=dict)
    before_summary: dict[str, object] = Field(default_factory=dict)
    after_summary: dict[str, object] = Field(default_factory=dict)
    request_time: datetime | None = None


class AdminAuditActor(BaseModel):
    """Authenticated administrator identity recorded by management audits."""

    model_config = ConfigDict(frozen=True)

    admin_user_id: str = Field(min_length=1)
    is_super: bool = False


class AuditActorType(StrEnum):
    """Supported actor identity namespaces."""

    ADMIN_USER = "admin_user"
    SYSTEM = "system"


class AuditActor(BaseModel):
    """Validated human or system actor used by resource audit fields."""

    model_config = ConfigDict(frozen=True)

    actor_type: AuditActorType
    actor_id: str | None

    @model_validator(mode="after")
    def validate_actor_id(self) -> AuditActor:
        if self.actor_type is AuditActorType.SYSTEM:
            if self.actor_id is not None:
                raise ValueError("system actor_id must be null")
            return self
        if self.actor_id is None or not self.actor_id.strip():
            raise ValueError("human actor_id must not be empty")
        try:
            parsed = UUID(self.actor_id)
        except ValueError as exc:
            raise ValueError("human actor_id must be a UUID4 hex ID") from exc
        if parsed.version != 4 or parsed.hex != self.actor_id:
            raise ValueError("human actor_id must be a lowercase UUID4 hex ID")
        return self

    @classmethod
    def admin_user(cls, actor_id: str) -> AuditActor:
        return cls(actor_type=AuditActorType.ADMIN_USER, actor_id=actor_id)

    @classmethod
    def system(cls) -> AuditActor:
        return cls(actor_type=AuditActorType.SYSTEM, actor_id=None)
