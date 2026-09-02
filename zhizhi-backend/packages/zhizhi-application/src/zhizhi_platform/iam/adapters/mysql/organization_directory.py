"""Bounded read-only queries over arbitrary-depth organization trees."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zhizhi_platform.iam.adapters.mysql.models import OrganizationUnitModel
from zhizhi_platform.iam.errors import OrganizationDirectoryCapacityExceededError
from zhizhi_platform.iam.ports import OrganizationDirectoryEntry

SessionFactory = Callable[[], AsyncSession]
ACTIVE_STATUS = "active"


class MysqlOrganizationDirectory:
    def __init__(self, session_factory: SessionFactory, *, max_query_rows: int = 10_000) -> None:
        self._sessions = session_factory
        self._max_query_rows = max_query_rows

    async def descendant_ids(self, organization_unit_ids: Sequence[str]) -> Sequence[str]:
        roots = tuple(dict.fromkeys(value for value in organization_unit_ids if value))
        if not roots:
            return ()
        async with self._sessions() as session:
            rows = tuple(
                await session.execute(
                    select(
                        OrganizationUnitModel.id,
                        OrganizationUnitModel.parent_id,
                    ).where(OrganizationUnitModel.status == ACTIVE_STATUS)
                )
            )
        self._require_capacity(rows, "Organization descendant lookup")
        children: dict[str, list[str]] = {}
        for unit_id, parent_id in rows:
            if parent_id:
                children.setdefault(str(parent_id), []).append(str(unit_id))
        descendants: list[str] = []
        pending = list(roots)
        seen = set(roots)
        while pending:
            parent_id = pending.pop()
            for child_id in children.get(parent_id, []):
                if child_id in seen:
                    continue
                seen.add(child_id)
                descendants.append(child_id)
                pending.append(child_id)
        self._require_capacity(descendants, "Organization descendant lookup")
        return tuple(descendants)

    async def search_organization_unit_ids(
        self,
        keyword: str,
        *,
        include_descendants: bool = False,
    ) -> Sequence[str]:
        normalized = keyword.strip()
        if not normalized:
            return ()
        pattern = f"%{normalized}%"
        async with self._sessions() as session:
            matched = tuple(
                await session.scalars(
                    select(OrganizationUnitModel.id)
                    .where(
                        OrganizationUnitModel.status == ACTIVE_STATUS,
                        or_(
                            OrganizationUnitModel.name.ilike(pattern),
                            OrganizationUnitModel.external_key.ilike(pattern),
                            OrganizationUnitModel.unit_type.ilike(pattern),
                        ),
                    )
                    .limit(self._max_query_rows + 1)
                )
            )
        self._require_capacity(matched, "Organization search")
        if not include_descendants:
            return tuple(str(value) for value in matched)
        descendants = await self.descendant_ids(tuple(str(value) for value in matched))
        return tuple(dict.fromkeys((*matched, *descendants)))

    async def list_active_by_external_keys(
        self, tenant_id: str, external_keys: Sequence[str]
    ) -> Sequence[OrganizationDirectoryEntry]:
        keys = tuple(dict.fromkeys(key.strip().upper() for key in external_keys if key.strip()))
        if not keys:
            return ()
        async with self._sessions() as session:
            rows = tuple(
                await session.scalars(
                    select(OrganizationUnitModel)
                    .where(
                        OrganizationUnitModel.tenant_id == tenant_id,
                        OrganizationUnitModel.normalized_external_key.in_(keys),
                        OrganizationUnitModel.status == ACTIVE_STATUS,
                    )
                    .limit(self._max_query_rows + 1)
                )
            )
        self._require_capacity(rows, "Organization exact lookup")
        return tuple(
            OrganizationDirectoryEntry(
                id=row.id,
                tenant_id=row.tenant_id,
                external_key=row.external_key,
                name=row.name,
                unit_type=row.unit_type,
                parent_id=row.parent_id or "",
                status=row.status,
            )
            for row in rows
        )

    def _require_capacity(self, values: Sequence[object], operation: str) -> None:
        if len(values) > self._max_query_rows:
            raise OrganizationDirectoryCapacityExceededError(operation, self._max_query_rows)
