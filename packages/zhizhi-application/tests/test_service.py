from typing import Any, cast

import pytest

from gewu_agent_runtime.domain import StoredAttachment
from gewu_agent_runtime.persistence import InMemoryRuntimeStore
from gewu_core.errors import ApplicationError
from zhizhi.contracts import (
    AgentContext,
    AgentTurnCommand,
    AgentUploadAttachmentCommand,
)
from zhizhi.provider import ZhizhiRuntimeProvider
from zhizhi.scope import AgentScope
from zhizhi.service import AgentWorkbenchService
from zhizhi_platform.iam import OrganizationUnitRef


class _Scopes:
    async def resolve(self, **_: str) -> AgentScope:
        return AgentScope(
            tenant_id="tenant-id",
            tenant_code="TENANT",
            tenant_storage_key="tenant-key",
            organization_path=(
                OrganizationUnitRef(
                    id="division-id",
                    external_key="division",
                    storage_key="division-key",
                    name="Division",
                ),
                OrganizationUnitRef(
                    id="team-id",
                    external_key="team",
                    storage_key="team-key",
                    name="Team",
                ),
            ),
            principal_id="user-1",
            principal_type="user",
        )


class _UnusedCapabilities:
    support_vision = True

    async def resolve(self, _: AgentScope) -> Any:
        raise AssertionError("bindings must remain lazy in this test")

    async def supports_vision(self, _: AgentScope) -> bool:
        return self.support_vision


class _Media:
    storage_backend = "memory"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def save(self, resource_key: str, data: bytes, mime_type: str) -> None:
        del mime_type
        self.objects[resource_key] = data

    async def read(self, resource_key: str) -> bytes:
        return self.objects[resource_key]

    async def delete(self, resource_key: str) -> None:
        self.objects.pop(resource_key, None)

    async def close(self) -> None:
        pass


class _Runtime:
    async def start_prepared_turn(self, prepared: Any) -> str:
        return prepared.request.conversation_id


async def test_first_turn_persists_trusted_conversation_metadata() -> None:
    store = InMemoryRuntimeStore()
    provider = ZhizhiRuntimeProvider(
        subscriber_id="zhizhi",
        scopes=_Scopes(),
        capabilities=_UnusedCapabilities(),
    )
    service = AgentWorkbenchService(
        runtime=cast(Any, _Runtime()),
        store=store,
        provider=provider,
    )
    command = AgentTurnCommand(
        conversation_id="conversation-1",
        content="question",
        request_id="request-1",
        tenant_id="tenant-id",
        active_organization_unit_id="team-id",
        principal_id="user-1",
        principal_type="user",
        metadata={"host_trace_id": "trace-1"},
    )

    conversation_id = await service.start_turn(command)
    conversation = await store.get_conversation(conversation_id)

    assert conversation is not None
    assert conversation.owner.principal_id == "user-1"
    assert conversation.metadata["host_trace_id"] == "trace-1"
    assert conversation.metadata["zhizhi"] == {
        "conversation_id": "conversation-1",
        "tenant_id": "tenant-id",
        "active_organization_unit_id": "team-id",
        "principal_id": "user-1",
        "principal_type": "user",
    }


def _context() -> AgentContext:
    return AgentContext(
        conversation_id="conversation-1",
        tenant_id="tenant-id",
        active_organization_unit_id="team-id",
        principal_id="user-1",
        principal_type="user",
    )


async def test_image_upload_creates_workbench_conversation_and_can_be_reused_by_turn() -> None:
    store = InMemoryRuntimeStore()
    capabilities = _UnusedCapabilities()
    media = _Media()
    provider = ZhizhiRuntimeProvider(
        subscriber_id="zhizhi",
        scopes=_Scopes(),
        capabilities=capabilities,
        attachment_loader=media,
    )
    runtime = _Runtime()
    service = AgentWorkbenchService(
        runtime=cast(Any, runtime),
        store=store,
        provider=provider,
        media=media,
        max_image_bytes=1024,
        max_images_per_message=4,
    )

    attachment = await service.upload_attachment(
        AgentUploadAttachmentCommand(
            **_context().model_dump(),
            request_id="request-image-1",
            data=b"\x89PNG\r\n\x1a\nimage-data",
        )
    )
    result = await service.start_turn(
        AgentTurnCommand(
            **_context().model_dump(),
            request_id="request-image-1",
            attachment_ids=(attachment.attachment_id,),
        )
    )

    assert result == provider.conversation_id("conversation-1", "user-1")
    stored = await store.get_active_attachment(attachment.attachment_id, attachment.owner)
    assert isinstance(stored, StoredAttachment)
    assert await service.read_attachment_data(stored) == b"\x89PNG\r\n\x1a\nimage-data"


async def test_image_upload_rejects_model_without_vision_support() -> None:
    store = InMemoryRuntimeStore()
    capabilities = _UnusedCapabilities()
    capabilities.support_vision = False
    media = _Media()
    provider = ZhizhiRuntimeProvider(
        subscriber_id="zhizhi",
        scopes=_Scopes(),
        capabilities=capabilities,
        attachment_loader=media,
    )
    service = AgentWorkbenchService(
        runtime=cast(Any, _Runtime()),
        store=store,
        provider=provider,
        media=media,
    )

    with pytest.raises(ApplicationError, match="does not support image"):
        await service.upload_attachment(
            AgentUploadAttachmentCommand(
                **_context().model_dump(),
                request_id="request-image-1",
                data=b"\x89PNG\r\n\x1a\nimage-data",
            )
        )
