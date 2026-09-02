"""Public endpoints for one-time Zhizhi installation."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from zhizhi_admin_api.dependencies import AdminBootstrapServiceDep
from zhizhi_platform.iam import AdminSeedError, InstallationStatus

router = APIRouter(prefix="/api/admin/bootstrap", tags=["admin-bootstrap"])


class BootstrapStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    bootstrap_enabled: bool


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bootstrap_token: str = Field(min_length=1)
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="超级管理员", min_length=1, max_length=128)
    encrypted_password: str = Field(min_length=1)


def _response(
    service: AdminBootstrapServiceDep,
    status: InstallationStatus,
) -> BootstrapStatusResponse:
    return BootstrapStatusResponse(
        state=status.state.value,
        bootstrap_enabled=service.bootstrap_enabled(status),
    )


@router.get("/status", response_model=BootstrapStatusResponse)
async def bootstrap_status(
    service: AdminBootstrapServiceDep,
) -> BootstrapStatusResponse:
    """Return durable installation state without exposing account details."""

    return _response(service, await service.status())


@router.post("", response_model=BootstrapStatusResponse)
async def initialize_bootstrap(
    payload: BootstrapRequest,
    service: AdminBootstrapServiceDep,
) -> BootstrapStatusResponse:
    """Create the first super administrator and permanently seal setup."""

    try:
        status = await service.initialize(
            bootstrap_token=payload.bootstrap_token,
            username=payload.username,
            display_name=payload.display_name,
            encrypted_password=payload.encrypted_password,
        )
    except AdminSeedError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return _response(service, status)
