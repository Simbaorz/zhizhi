"""MySQL-backed tenant and active organization scope resolution."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from zhizhi import AgentScope
from zhizhi_platform.iam import OrganizationUnitRef

_TENANT_SQL = text("""
    SELECT id, tenant_code, storage_key
    FROM zhizhi_tenant
    WHERE id = :tenant_id AND status = 'active'
    LIMIT 1
    """)

_ORGANIZATION_UNIT_SQL = text("""
    SELECT id, tenant_id, parent_id, external_key, storage_key, name, unit_type
    FROM zhizhi_organization_unit
    WHERE id = :organization_unit_id
      AND tenant_id = :tenant_id
      AND status = 'active'
    LIMIT 1
    """)


class MysqlAgentScopeResolver:
    """Resolve a tenant and validate the complete root-to-leaf parent path."""

    def __init__(self, engine: AsyncEngine, *, max_depth: int = 64) -> None:
        self._engine = engine
        self._max_depth = max_depth

    async def resolve(
        self,
        *,
        tenant_id: str,
        active_organization_unit_id: str,
        principal_id: str,
        principal_type: str,
    ) -> AgentScope | None:
        async with self._engine.connect() as connection:
            tenant = (
                (await connection.execute(_TENANT_SQL, {"tenant_id": tenant_id.strip()}))
                .mappings()
                .first()
            )
            if tenant is None:
                return None
            reversed_path: list[OrganizationUnitRef] = []
            current_id = active_organization_unit_id.strip()
            visited: set[str] = set()
            while current_id:
                if current_id in visited or len(visited) >= self._max_depth:
                    return None
                visited.add(current_id)
                row = (
                    (
                        await connection.execute(
                            _ORGANIZATION_UNIT_SQL,
                            {
                                "tenant_id": tenant_id.strip(),
                                "organization_unit_id": current_id,
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    return None
                reversed_path.append(
                    OrganizationUnitRef(
                        id=str(row["id"]),
                        external_key=str(row["external_key"]),
                        name=str(row["name"] or ""),
                        unit_type=str(row["unit_type"] or ""),
                        storage_key=str(row["storage_key"] or ""),
                    )
                )
                current_id = str(row["parent_id"] or "")
        return AgentScope(
            tenant_id=str(tenant["id"]),
            tenant_code=str(tenant["tenant_code"]),
            tenant_storage_key=str(tenant["storage_key"]),
            organization_path=tuple(reversed(reversed_path)),
            principal_id=principal_id,
            principal_type=principal_type,
        )
