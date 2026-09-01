"""Tenant and arbitrary-depth organization-unit resource scopes."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zhizhi_platform.iam.errors import PermissionDeniedError


class ScopeType(StrEnum):
    """Resource ownership level independent of organization depth."""

    TENANT = "tenant"
    ORGANIZATION_UNIT = "organization_unit"


class OrganizationUnitRef(BaseModel):
    """One node in an active organization path, ordered root to leaf."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    external_key: str = Field(min_length=1)
    name: str = ""
    unit_type: str = ""
    storage_key: str = ""

    @property
    def display_name(self) -> str:
        return self.name or self.external_key


class AccessScope(BaseModel):
    """Actor or resource scope inside one active tenant."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(min_length=1)
    tenant_storage_key: str = ""
    scope_type: ScopeType
    organization_path: tuple[OrganizationUnitRef, ...] = Field(default_factory=tuple)
    principal_id: str = ""
    principal_type: str = "user"
    tenant_name: str = ""
    principal_name: str = ""

    @model_validator(mode="after")
    def validate_required_identifiers(self) -> AccessScope:
        if self.scope_type is ScopeType.ORGANIZATION_UNIT and not self.organization_path:
            raise ValueError("organization_path is required for organization_unit scope.")
        if len({unit.id for unit in self.organization_path}) != len(self.organization_path):
            raise ValueError("organization_path cannot contain duplicate units.")
        return self

    @property
    def organization_unit_id(self) -> str:
        return self.organization_path[-1].id if self.organization_path else ""

    @property
    def organization_unit_ids(self) -> tuple[str, ...]:
        return tuple(unit.id for unit in self.organization_path)

    def can_read(self, resource_scope: AccessScope) -> bool:
        if self.tenant_id != resource_scope.tenant_id:
            return False
        if resource_scope.scope_type is ScopeType.TENANT:
            return True
        return resource_scope.organization_unit_id in self.organization_unit_ids

    def can_write(self, resource_scope: AccessScope) -> bool:
        """Runtime workspaces are read-only in the first open-source release."""

        return False

    def require_read(self, resource_scope: AccessScope) -> None:
        if not self.can_read(resource_scope):
            raise PermissionDeniedError("Resource is not readable from current scope.")

    def require_write(self, resource_scope: AccessScope) -> None:
        if not self.can_write(resource_scope):
            raise PermissionDeniedError("Runtime workspace writes are disabled.")

    def shared_ancestor_scopes(self) -> list[AccessScope]:
        scopes = [
            AccessScope(
                tenant_id=self.tenant_id,
                tenant_storage_key=self.tenant_storage_key,
                scope_type=ScopeType.TENANT,
                tenant_name=self.tenant_display_name,
            )
        ]
        for index in range(len(self.organization_path)):
            scopes.append(
                AccessScope(
                    tenant_id=self.tenant_id,
                    tenant_storage_key=self.tenant_storage_key,
                    scope_type=ScopeType.ORGANIZATION_UNIT,
                    organization_path=self.organization_path[: index + 1],
                    tenant_name=self.tenant_display_name,
                )
            )
        return scopes

    def shared_mount_scopes(self) -> list[AccessScope]:
        return self.shared_ancestor_scopes()

    @property
    def tenant_display_name(self) -> str:
        return self.tenant_name or self.tenant_id

    @property
    def organization_display_name(self) -> str:
        return (
            self.organization_path[-1].display_name
            if self.organization_path
            else self.tenant_display_name
        )

    @property
    def principal_display_name(self) -> str:
        return self.principal_name or self.principal_id
