"""致知 IAM organization row compatibility exports."""

from zhizhi_platform.iam.adapters.mysql.models.organization import (
    OrganizationUnitModel,
    TenantModel,
)

__all__ = [
    "OrganizationUnitModel",
    "TenantModel",
]
