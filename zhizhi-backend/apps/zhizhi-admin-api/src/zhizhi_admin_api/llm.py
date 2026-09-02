"""致知 model configuration, entitlement, and binding management routes."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from zhizhi_admin_api.dependencies import AdminSessionDep, LLMAdminServiceDep
from zhizhi_platform.llm import (
    CreateLLMBindingCommand,
    CreateLLMConfigCommand,
    CreateLLMEntitlementCommand,
    CreateLLMEntitlementsCommand,
    UpdateLLMBindingCommand,
    UpdateLLMConfigCommand,
)

router = APIRouter(prefix="/api/admin/llm", tags=["admin"])
PageQuery = Annotated[int, Query(ge=1)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]
SearchQuery = Annotated[str, Query(max_length=128)]


class LLMConfigCreateRequest(BaseModel):
    """Model configuration create request."""

    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1)
    display_name: str = ""
    provider: Literal["openai", "anthropic"]
    protocol: Literal["openai-chat", "anthropic-messages"]
    model_name: str = Field(min_length=1)
    endpoint_url: str = ""
    status: str = "active"
    support_stream: bool = True
    support_tools: bool = True
    support_vision: bool = False
    support_thinking: bool = False
    timeout_seconds: int = 600
    generation_config: dict[str, Any] = Field(default_factory=dict)
    provider_config: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] = Field(default_factory=dict)


class LLMConfigUpdateRequest(BaseModel):
    """Model configuration update request."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    model_name: str | None = None
    endpoint_url: str | None = None
    status: str | None = None
    support_stream: bool | None = None
    support_tools: bool | None = None
    support_vision: bool | None = None
    support_thinking: bool | None = None
    timeout_seconds: int | None = None
    generation_config: dict[str, Any] | None = None
    provider_config: dict[str, Any] | None = None


class LLMBindingCreateRequest(BaseModel):
    """Model binding create request."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    scope_type: Literal["tenant", "organization_unit"]
    organization_unit_id: str = ""
    llm_config_id: str = Field(min_length=1)
    status: str = "active"
    runtime_overrides: dict[str, Any] = Field(default_factory=dict)


class LLMEntitlementCreateRequest(BaseModel):
    """Model pool entry create request."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    scope_type: Literal["tenant", "organization_unit"]
    organization_unit_id: str = ""
    llm_config_id: str = Field(min_length=1)
    status: str = "active"


class LLMEntitlementBatchCreateRequest(BaseModel):
    """Model pool batch create request."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    scope_type: Literal["tenant", "organization_unit"]
    organization_unit_id: str = ""
    llm_config_ids: list[str] = Field(min_length=1, max_length=10)
    status: str = "active"


class LLMEntitlementUpdateRequest(BaseModel):
    """Model pool entry update request."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = None


class LLMBindingUpdateRequest(BaseModel):
    """Model binding update request."""

    model_config = ConfigDict(extra="forbid")

    llm_config_id: str | None = Field(default=None, min_length=1)
    status: str | None = None
    runtime_overrides: dict[str, Any] | None = None


class LLMCredentialUpdateRequest(BaseModel):
    """Model credential update request."""

    model_config = ConfigDict(extra="forbid")

    credentials: dict[str, Any] = Field(default_factory=dict)


class LLMTestRequest(BaseModel):
    """Model connectivity test request."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(default="你好，请用一句话介绍自己。", min_length=1)
    system_prompt: str = ""


@router.get("/models")
async def list_models(
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
    search: SearchQuery = "",
    status: str = "all",
    provider: Literal["all", "openai", "anthropic"] = "all",
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    tenant_id: str | None = None,
) -> dict[str, object]:
    """List model configurations."""

    result = await service.list_models(
        session_user,
        tenant_id=tenant_id,
        search=search,
        status=status,
        provider=provider,
        page=page,
        page_size=page_size,
    )
    return {
        "models": list(result.items),
        "pagination": {"page": page, "page_size": page_size, "total": result.total},
    }


@router.post("/models")
async def create_model(
    payload: LLMConfigCreateRequest,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Create one model configuration."""

    return await service.create_config(
        session_user,
        CreateLLMConfigCommand.model_validate(payload.model_dump()),
    )


@router.patch("/models/{model_id}")
async def update_model(
    model_id: str,
    payload: LLMConfigUpdateRequest,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Update one model configuration."""

    return await service.update_config(
        session_user,
        model_id,
        UpdateLLMConfigCommand.model_validate(payload.model_dump()),
    )


@router.delete("/models/{model_id}")
async def delete_model(
    model_id: str,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Delete one model configuration."""

    return await service.delete_config(session_user, model_id)


@router.put("/models/{model_id}/credentials")
async def update_model_credentials(
    model_id: str,
    payload: LLMCredentialUpdateRequest,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Update one model credential payload."""

    return await service.update_credentials(session_user, model_id, payload.credentials)


@router.post("/models/{model_id}/validate")
async def validate_model(
    model_id: str,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Validate one model configuration locally."""

    return await service.validate_config(session_user, model_id)


@router.post("/models/{model_id}/test")
async def test_model(
    model_id: str,
    payload: LLMTestRequest,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Run one admin-only model connectivity test."""

    return await service.test_config(
        session_user,
        model_id,
        prompt=payload.prompt,
        system_prompt=payload.system_prompt,
    )


@router.get("/bindings")
async def list_bindings(
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
    tenant_id: str | None = None,
    search: SearchQuery = "",
    status: str = "all",
    scope_type: str = "all",
    organization_unit_id: str = "",
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict[str, object]:
    """List model bindings for tenant or organization-unit scopes."""

    result = await service.list_bindings(
        session_user,
        tenant_id=tenant_id,
        search=search,
        status=status,
        scope_type=scope_type,
        organization_unit_id=organization_unit_id,
        page=page,
        page_size=page_size,
    )
    return {
        "bindings": list(result.items),
        "pagination": {"page": page, "page_size": page_size, "total": result.total},
    }


@router.get("/entitlements")
async def list_entitlements(
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
    tenant_id: str | None = None,
    search: str = "",
    status: str = "all",
    scope_type: str = "all",
    organization_unit_id: str = "",
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> dict[str, object]:
    """List available models for tenant or organization-unit scopes."""

    result = await service.list_entitlements(
        session_user,
        tenant_id=tenant_id,
        search=search,
        status=status,
        scope_type=scope_type,
        organization_unit_id=organization_unit_id,
        page=page,
        page_size=page_size,
    )
    return {
        "entitlements": list(result.items),
        "pagination": {"page": page, "page_size": page_size, "total": result.total},
    }


@router.post("/entitlements")
async def create_entitlement(
    payload: LLMEntitlementCreateRequest,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Create one available-model entry for an organization scope."""

    return await service.create_entitlement(
        CreateLLMEntitlementCommand.model_validate(payload.model_dump()),
        session_user,
    )


@router.post("/entitlements/batch")
async def create_entitlements(
    payload: LLMEntitlementBatchCreateRequest,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Create available-model entries for an organization scope."""

    return await service.create_entitlements(
        CreateLLMEntitlementsCommand.model_validate(payload.model_dump()),
        session_user,
    )


@router.patch("/entitlements/{entitlement_id}")
async def update_entitlement(
    entitlement_id: str,
    payload: LLMEntitlementUpdateRequest,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Update one available-model entry."""

    return await service.update_entitlement(
        entitlement_id,
        status=payload.status,
        session_user=session_user,
    )


@router.delete("/entitlements/{entitlement_id}")
async def delete_entitlement(
    entitlement_id: str,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Delete one available-model entry."""

    return await service.delete_entitlement(entitlement_id, session_user)


@router.post("/bindings")
async def create_binding(
    payload: LLMBindingCreateRequest,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Bind one model to an organization scope."""

    return await service.create_binding(
        CreateLLMBindingCommand.model_validate(payload.model_dump()),
        session_user,
    )


@router.patch("/bindings/{binding_id}")
async def update_binding(
    binding_id: str,
    payload: LLMBindingUpdateRequest,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Update one organization-scope model binding."""

    return await service.update_binding(
        binding_id,
        UpdateLLMBindingCommand.model_validate(payload.model_dump()),
        session_user,
    )


@router.delete("/bindings/{binding_id}")
async def delete_binding(
    binding_id: str,
    session_user: AdminSessionDep,
    service: LLMAdminServiceDep,
) -> dict[str, object]:
    """Delete one organization-scope model binding."""

    return await service.delete_binding(binding_id, session_user)
