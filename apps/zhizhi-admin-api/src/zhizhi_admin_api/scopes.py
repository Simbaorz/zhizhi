"""Admin scope catalog route."""

from fastapi import APIRouter

from zhizhi_admin_api.dependencies import (
    AdminSessionDep,
    OrganizationAdminServiceDep,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/scope-catalog")
async def scope_catalog(
    session_user: AdminSessionDep,
    service: OrganizationAdminServiceDep,
) -> dict[str, object]:
    """Return scopes visible to the current admin session."""

    scopes = await service.scope_catalog(session_user)
    return {
        "scopes": [
            scope for scope in scopes if _scope_type(scope) in {"tenant", "organization_unit"}
        ]
    }


def _scope_type(node: dict[str, object]) -> str:
    value = node.get("scope")
    if not isinstance(value, dict):
        return ""
    return str(value.get("scope_type") or "")
