"""Compatibility re-exports for Data Source tables owned by their resource package."""

from zhizhi_platform.data_source.adapters.mysql.models import (
    DataSourceSourceBindingModel,
    DataSourceSourceEntitlementModel,
    DataSourceSourceModel,
)

__all__ = [
    "DataSourceSourceBindingModel",
    "DataSourceSourceEntitlementModel",
    "DataSourceSourceModel",
]
