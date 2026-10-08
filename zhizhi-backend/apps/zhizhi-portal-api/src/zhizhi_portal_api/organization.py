"""Read-only platform identity and arbitrary-depth organization lookup."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from zhizhi_platform.iam.codes import canonical_stable_code


class OrganizationReader:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def admin(self, value: str, *, by_id: bool = False) -> dict[str, Any] | None:
        field = "id" if by_id else "normalized_username"
        async with self.engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"SELECT id, username, display_name, email, password_hash, token_version FROM zhizhi_admin_user WHERE {field}=:value AND is_super=1 AND status='active'"
                        ),
                        {"value": value if by_id else canonical_stable_code(value)},
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    async def tenants(self) -> list[dict[str, Any]]:
        async with self.engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT id, tenant_code, tenant_name FROM zhizhi_tenant WHERE status='active' ORDER BY tenant_name, tenant_code"
                        )
                    )
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    async def scopes(self, tenant_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as connection:
            tenant = (
                (
                    await connection.execute(
                        text(
                            "SELECT id, tenant_code, tenant_name FROM zhizhi_tenant WHERE id=:id AND status='active'"
                        ),
                        {"id": tenant_id},
                    )
                )
                .mappings()
                .first()
            )
            if not tenant:
                return []
            units = (
                (
                    await connection.execute(
                        text(
                            "SELECT id, parent_id, name FROM zhizhi_organization_unit WHERE tenant_id=:id AND status='active' ORDER BY sort_order, name, id"
                        ),
                        {"id": tenant_id},
                    )
                )
                .mappings()
                .all()
            )
        lookup = {str(row["id"]): row for row in units}
        result = [
            {
                **tenant,
                "tenant_id": tenant_id,
                "organization_unit_id": "",
                "organization_path": [],
                "label": "租户范围",
            }
        ]
        for unit in units:
            path: list[str] = []
            current = str(unit["id"])
            seen: set[str] = set()
            while current:
                if current in seen or current not in lookup or len(seen) >= 64:
                    break
                seen.add(current)
                row = lookup[current]
                path.append(str(row["name"]))
                current = str(row["parent_id"] or "")
            else:
                path.reverse()
                result.append(
                    {
                        **tenant,
                        "tenant_id": tenant_id,
                        "organization_unit_id": str(unit["id"]),
                        "organization_path": path,
                        "label": " / ".join(path),
                    }
                )
        return result

    async def scope(self, tenant_id: str, organization_unit_id: str) -> dict[str, Any] | None:
        return next(
            (
                scope
                for scope in await self.scopes(tenant_id)
                if scope["organization_unit_id"] == organization_unit_id
            ),
            None,
        )
