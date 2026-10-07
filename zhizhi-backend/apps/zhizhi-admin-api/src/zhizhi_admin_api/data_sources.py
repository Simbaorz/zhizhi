"""Data-source configuration, delegation, multi-source binding and MCP probes."""

from collections.abc import Callable, Coroutine
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from zhizhi_admin_api.dependencies import AdminSessionDep
from zhizhi_platform.data_source.domain import SourceBinding, SourceEntitlement
from zhizhi_platform.data_source.mcp_client import DataMcpClient
from zhizhi_platform.data_source.service import DataSourceAdminService
from zhizhi_platform.iam import ensure_super_admin


class DataSourceRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def sanitized(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": "数据源请求参数无效。",
                        "errors": [
                            {"loc": list(item["loc"]), "type": item["type"], "msg": item["msg"]}
                            for item in exc.errors()
                        ],
                    },
                )

        return sanitized


router = APIRouter(prefix="/api/admin/data-sources", tags=["admin"], route_class=DataSourceRoute)


def service(request: Request) -> DataSourceAdminService:
    value = getattr(getattr(request.app.state, "runtime", None), "data_source_service", None)
    if not isinstance(value, DataSourceAdminService):
        raise HTTPException(503, "Data source management is unavailable.")
    return value


_SERVICE = Depends(service)


class SourceWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_key: str
    tag: str
    display_name: str = ""
    description: str = ""
    driver: Literal["mysql", "postgresql"] = "mysql"
    host: str
    port: int = Field(default=3306, ge=1, le=65535)
    database: str
    username: str
    password: str | None = Field(default=None, repr=False, max_length=4096)
    revision: int | None = Field(default=None, ge=1)
    server_id: str = "main"
    endpoint_url: str = "http://127.0.0.1:8002/mcp"
    status: Literal["active", "inactive"] = "active"
    pool_size: int = Field(default=3, ge=1, le=32)
    pool_timeout_seconds: float = Field(default=5, gt=0, le=60)
    connect_timeout_seconds: float = Field(default=5, gt=0, le=60)
    query_timeout_seconds: float = Field(default=30, gt=0, le=300)
    max_rows: int = Field(default=500, ge=1, le=10000)
    max_result_bytes: int = Field(default=262144, ge=2048, le=1048576)
    allowed_schemas: tuple[str, ...] = ()
    tls: bool = False


@router.get("")
async def list_sources(
    user: AdminSessionDep,
    management: DataSourceAdminService = _SERVICE,
    tenant_id: str = "",
    organization_unit_id: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str = "",
) -> dict[str, object]:
    return await management.list_sources(
        user,
        tenant_id=tenant_id,
        unit_id=organization_unit_id,
        page=page,
        page_size=page_size,
        search=search,
    )


@router.post("")
async def create_source(
    payload: SourceWriteRequest,
    user: AdminSessionDep,
    management: DataSourceAdminService = _SERVICE,
) -> dict[str, object]:
    return await management.save_source(
        user, payload.model_dump(exclude={"password"}), payload.password
    )


@router.get("/assignable")
async def assignable(
    user: AdminSessionDep,
    tenant_id: str,
    organization_unit_id: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str = "",
    management: DataSourceAdminService = _SERVICE,
) -> dict[str, object]:
    return await management.assignable(
        user, tenant_id, organization_unit_id, page, page_size, search
    )


@router.get("/entitlements")
async def entitlements(
    user: AdminSessionDep,
    tenant_id: str,
    organization_unit_id: str = "",
    management: DataSourceAdminService = _SERVICE,
) -> dict[str, object]:
    return await management.list_resources(
        user, tenant_id, organization_unit_id, kind="entitlements"
    )


@router.post("/entitlements")
async def grant(
    payload: SourceEntitlement,
    user: AdminSessionDep,
    management: DataSourceAdminService = _SERVICE,
) -> dict[str, Any]:
    return (await management.grant(user, payload)).model_dump(mode="json")


@router.delete("/entitlements")
async def revoke(
    user: AdminSessionDep,
    tenant_id: str,
    source_id: str,
    organization_unit_id: str = "",
    management: DataSourceAdminService = _SERVICE,
) -> dict[str, bool]:
    await management.revoke(user, tenant_id, organization_unit_id, source_id)
    return {"deleted": True}


@router.get("/bindings")
async def bindings(
    user: AdminSessionDep,
    tenant_id: str,
    organization_unit_id: str = "",
    management: DataSourceAdminService = _SERVICE,
) -> dict[str, object]:
    return await management.list_resources(user, tenant_id, organization_unit_id, kind="bindings")


@router.put("/bindings")
async def bind(
    payload: SourceBinding,
    user: AdminSessionDep,
    management: DataSourceAdminService = _SERVICE,
) -> dict[str, Any]:
    return (await management.bind(user, payload)).model_dump(mode="json")


@router.delete("/bindings")
async def unbind(
    user: AdminSessionDep,
    tenant_id: str,
    organization_unit_id: str = "",
    management: DataSourceAdminService = _SERVICE,
) -> dict[str, bool]:
    await management.unbind(user, tenant_id, organization_unit_id)
    return {"deleted": True}


@router.put("/{source_id}")
async def update_source(
    source_id: str,
    payload: SourceWriteRequest,
    user: AdminSessionDep,
    management: DataSourceAdminService = _SERVICE,
) -> dict[str, object]:
    return await management.save_source(
        user, payload.model_dump(exclude={"password"}), payload.password, source_id=source_id
    )


@router.delete("/{source_id}")
async def delete_source(
    source_id: str, user: AdminSessionDep, management: DataSourceAdminService = _SERVICE
) -> dict[str, bool]:
    await management.delete_source(user, source_id)
    return {"deleted": True}


@router.post("/{source_id}/test")
async def test_source(
    source_id: str,
    request: Request,
    user: AdminSessionDep,
    management: DataSourceAdminService = _SERVICE,
) -> dict[str, object]:
    ensure_super_admin(user)
    source = await management.require_source(source_id)
    client: DataMcpClient = request.app.state.runtime.data_mcp_client
    try:
        result = await client.query(
            source, None, "SELECT 1 AS connected", {}, "connection_test", probe=True
        )
        success = result.get("connected") is True
    except Exception:
        success = False
    await management.repository.record_test(
        source.id, "success" if success else "failed", source.revision
    )
    return {
        "success": success,
        "message": (
            "MCP 数据库连接成功。"
            if success
            else "连接失败，请检查 MCP 服务、签名密钥、数据源配置和数据库网络。"
        ),
    }
