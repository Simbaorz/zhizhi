"""Organization facts used by data-source grants and runtime authorization."""

from collections.abc import Sequence
from typing import Protocol

from zhizhi_platform.iam.models import ManagedOrganizationUnit, ManagedTenant


class DataSourceOrganizationDirectory(Protocol):
    async def get_tenant(self, tenant_id: str) -> ManagedTenant | None: ...
    async def get_organization_unit(
        self, organization_unit_id: str
    ) -> ManagedOrganizationUnit | None: ...
    async def get_organization_path(
        self, tenant_id: str, organization_unit_id: str
    ) -> tuple[ManagedOrganizationUnit, ...]: ...
    async def descendant_ids(self, organization_unit_ids: Sequence[str]) -> Sequence[str]: ...
