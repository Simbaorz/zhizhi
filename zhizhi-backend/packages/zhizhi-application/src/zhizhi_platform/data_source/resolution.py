"""Resolve a complete nearest binding with grants checked across the active path."""

from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi_platform.data_source.domain import SourceSelection
from zhizhi_platform.data_source.repository import DataSourceRepository
from zhizhi_platform.iam import AccessScope


class DataSourceResolver:
    def __init__(self, repository: DataSourceRepository) -> None:
        self.repository = repository

    async def resolve(self, scope: AccessScope) -> SourceSelection | None:
        path = ["", *(unit.id for unit in scope.organization_path)]
        by_unit = {
            binding.organization_unit_id: binding
            for binding in await self.repository.list_bindings(scope.tenant_id, unit_ids=path)
            if binding.status == "active"
        }
        binding = next((by_unit[unit] for unit in reversed(path) if unit in by_unit), None)
        if binding is None:
            return None
        grants = {
            (item.organization_unit_id, item.source_id)
            for item in await self.repository.list_entitlements(
                scope.tenant_id, unit_ids=path, source_ids=binding.source_ids
            )
        }
        sources = []
        for source_id in binding.source_ids:
            if any((unit, source_id) not in grants for unit in path):
                raise ApplicationError(
                    ApplicationErrorKind.FORBIDDEN,
                    "A bound data source is no longer authorized on the active organization path.",
                )
            source = await self.repository.get_source(source_id)
            if source is None or source.status != "active":
                raise ApplicationError(
                    ApplicationErrorKind.UNAVAILABLE, "A bound data source is unavailable."
                )
            sources.append(source)
        if len({source.tag for source in sources}) != len(sources):
            raise ApplicationError(
                ApplicationErrorKind.CONFLICT,
                "The effective data-source selection contains duplicate tags.",
            )
        default = next(source.tag for source in sources if source.id == binding.default_source_id)
        return SourceSelection(
            sources=tuple(sorted(sources, key=lambda source: source.tag)), default_tag=default
        )
