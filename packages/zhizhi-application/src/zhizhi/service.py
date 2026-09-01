"""Zhizhi Web API use cases built on the Gewu Agent Runtime."""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

from gewu_agent_runtime import (
    AgentRuntime,
    AskAnswer,
    AttachmentRef,
    Conversation,
    ConversationMessage,
    PrincipalRef,
    RuntimeConversationSnapshot,
    TurnSession,
)
from gewu_agent_runtime.domain import StoredAttachment
from gewu_agent_runtime.persistence import ConcurrentWriteError, RuntimeStore
from gewu_core.errors import (
    ApplicationError,
    ApplicationErrorKind,
    CommitOutcomeUnknownError,
)
from gewu_core.ids import new_id
from zhizhi.contracts import (
    AgentContext,
    AgentTurnCommand,
    AgentUploadAttachmentCommand,
    AskAnswerCommand,
)
from zhizhi.provider import ZhizhiRuntimeProvider
from zhizhi_platform.chat_media import (
    ACCEPTED_IMAGE_MIME_TYPES,
    ZhizhiChatMediaStore,
    build_chat_media_resource_key,
    detect_image_upload_mime_type,
    image_extension_for_mime,
)

logger = logging.getLogger(__name__)


class MessagePage(BaseModel):
    """Newest-first page navigation with messages ordered for display."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    messages: tuple[ConversationMessage, ...] = ()
    has_more: bool = False
    next_before_sequence: int | None = Field(default=None, ge=1)
    run_state: str | None = None
    pending_ask: dict[str, object] | None = None


class ConversationStateView(BaseModel):
    """Minimal workbench state restored after the host page refreshes."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    run_state: str | None = None
    run_id: str | None = None
    pending_ask: dict[str, object] | None = None


class WorkbenchCapabilities(BaseModel):
    """Input capabilities and limits exposed to the external Agent workbench."""

    model_config = ConfigDict(frozen=True)

    support_vision: bool
    max_image_bytes: int = Field(ge=1)
    max_images_per_message: int = Field(ge=1)
    accepted_mime_types: tuple[str, ...] = ACCEPTED_IMAGE_MIME_TYPES


class AgentWorkbenchService:
    """Expose only the conversation operations needed by the embedded workbench."""

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        store: RuntimeStore,
        provider: ZhizhiRuntimeProvider,
        media: ZhizhiChatMediaStore | None = None,
        max_image_bytes: int = 5 * 1024 * 1024,
        max_images_per_message: int = 4,
    ) -> None:
        self._runtime = runtime
        self._store = store
        self._provider = provider
        self._media = media
        self._max_image_bytes = max_image_bytes
        self._max_images_per_message = max_images_per_message

    @property
    def max_image_bytes(self) -> int:
        return self._max_image_bytes

    async def capabilities(self, context: AgentContext) -> WorkbenchCapabilities:
        return WorkbenchCapabilities(
            support_vision=await self._provider.supports_vision(context),
            max_image_bytes=self._max_image_bytes,
            max_images_per_message=self._max_images_per_message,
        )

    async def start_turn(self, command: AgentTurnCommand) -> TurnSession:
        principal = self._provider.principal_for(command.principal_id, command.principal_type)
        await self._ensure_conversation(command, principal)
        attachments = await self._resolve_turn_attachments(command, principal)
        if attachments and not await self._provider.supports_vision(command):
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "The effective model does not support image input.",
            )
        prepared = await self._provider.prepare_turn(principal, command, attachments)
        return await self._runtime.start_prepared_turn(prepared)

    async def upload_attachment(
        self,
        command: AgentUploadAttachmentCommand,
    ) -> StoredAttachment:
        media = self._require_media()
        principal = self._provider.principal_for(command.principal_id, command.principal_type)
        if not await self._provider.supports_vision(command):
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "The effective model does not support image input.",
            )
        await self._ensure_conversation(command, principal)
        if len(command.data) > self._max_image_bytes:
            raise ApplicationError(
                ApplicationErrorKind.PAYLOAD_TOO_LARGE,
                "Image exceeds the configured maximum size.",
            )
        try:
            mime_type = detect_image_upload_mime_type(
                command.data,
                max_image_bytes=self._max_image_bytes,
            )
        except ValueError as exc:
            raise ApplicationError(ApplicationErrorKind.INVALID_INPUT, str(exc)) from exc
        attachment_id = new_id()
        resource_key = build_chat_media_resource_key(attachment_id, mime_type)
        await media.save(resource_key, command.data, mime_type)
        try:
            return await self._store.create_attachment(
                StoredAttachment(
                    attachment_id=attachment_id,
                    owner=principal,
                    conversation_id=self._conversation_id(command),
                    request_id=command.request_id,
                    storage_backend=media.storage_backend,
                    resource_key=resource_key,
                    original_name=(
                        f"image-{attachment_id[:8]}{image_extension_for_mime(mime_type)}"
                    ),
                    mime_type=mime_type,
                    size_bytes=len(command.data),
                )
            )
        except CommitOutcomeUnknownError:
            raise
        except BaseException:
            try:
                await media.delete(resource_key)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Unable to delete media after attachment metadata creation failed "
                    "attachment_id=%s exception_type=%s",
                    attachment_id,
                    type(exc).__name__,
                )
            raise

    async def resolve_attachment(
        self,
        context: AgentContext,
        attachment_id: str,
    ) -> StoredAttachment:
        await self._provider.resolve_scope(context)
        owner = self._provider.principal_for(context.principal_id, context.principal_type)
        attachment = await self._store.get_active_attachment(attachment_id, owner)
        if attachment is None or attachment.conversation_id != self._conversation_id(context):
            raise ApplicationError(ApplicationErrorKind.NOT_FOUND, "Attachment does not exist.")
        return attachment

    async def read_attachment_data(self, attachment: StoredAttachment) -> bytes:
        return await self._require_media().read(attachment.resource_key)

    async def list_messages(
        self,
        context: AgentContext,
        *,
        limit: int = 50,
        before_sequence: int | None = None,
    ) -> MessagePage:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        await self._provider.resolve_scope(context)
        conversation_id = self._conversation_id(context)
        snapshot = await self._inspect(context, resolve_expired_ask=True)
        if await self._store.get_conversation(conversation_id) is None:
            return MessagePage(conversation_id=conversation_id)
        candidates = await self._store.list_recent_messages(
            conversation_id,
            limit=limit + 1,
            before_sequence=before_sequence,
        )
        has_more = len(candidates) > limit
        messages = candidates[-limit:]
        return MessagePage(
            conversation_id=conversation_id,
            messages=messages,
            has_more=has_more,
            next_before_sequence=messages[0].sequence if has_more and messages else None,
            run_state=snapshot.run.status.value if snapshot.run is not None else None,
            pending_ask=snapshot.pending_ask,
        )

    async def state(self, context: AgentContext) -> ConversationStateView:
        await self._provider.resolve_scope(context)
        snapshot = await self._inspect(context, resolve_expired_ask=True)
        return ConversationStateView(
            conversation_id=self._conversation_id(context),
            run_state=snapshot.run.status.value if snapshot.run is not None else None,
            run_id=snapshot.run.run_id if snapshot.run is not None else None,
            pending_ask=snapshot.pending_ask,
        )

    async def resume_ask(self, command: AskAnswerCommand) -> TurnSession:
        scope = await self._provider.resolve_scope(command)
        principal = self._provider.principal_for(command.principal_id, command.principal_type)
        snapshot = await self._inspect(command, resolve_expired_ask=False)
        if snapshot.run is None or snapshot.pending_ask is None:
            from gewu_agent_runtime.runtime import AskNotPendingError

            raise AskNotPendingError("No pending ask_user request.")
        return await self._runtime.resume_ask(
            run_id=snapshot.run.run_id,
            invoker=principal,
            answer=AskAnswer(
                ask_id=command.ask_id,
                answers=command.answers,
                status=command.status,
                metadata=command.metadata,
            ),
            bindings_factory=lambda: self._provider.prepare_bindings(scope),
            request_id=command.request_id,
        )

    async def interrupt(self, context: AgentContext) -> bool:
        await self._provider.resolve_scope(context)
        principal = self._provider.principal_for(context.principal_id, context.principal_type)
        return await self._runtime.interrupt_conversation(
            self._conversation_id(context),
            principal,
            record_idle_interrupt=False,
        )

    def _conversation_id(self, context: AgentContext) -> str:
        return self._provider.conversation_id(context.conversation_id, context.principal_id)

    async def _inspect(
        self,
        context: AgentContext,
        *,
        resolve_expired_ask: bool,
    ) -> RuntimeConversationSnapshot:
        principal = self._provider.principal_for(context.principal_id, context.principal_type)
        return await self._runtime.inspect_conversation(
            self._conversation_id(context),
            principal,
            resolve_expired_ask=resolve_expired_ask,
        )

    async def _ensure_conversation(
        self,
        command: AgentContext,
        principal: PrincipalRef,
    ) -> None:
        conversation_id = self._conversation_id(command)
        existing = await self._store.get_conversation(conversation_id)
        if existing is None:
            conversation = Conversation(
                conversation_id=conversation_id,
                owner=self._provider.principal_for(command.principal_id, command.principal_type),
                title=command.conversation_id,
                metadata={
                    **command.metadata,
                    "zhizhi": {
                        "conversation_id": command.conversation_id,
                        "tenant_id": command.tenant_id,
                        "active_organization_unit_id": (command.active_organization_unit_id),
                        "principal_id": command.principal_id,
                        "principal_type": command.principal_type,
                    },
                },
            )
            try:
                existing = await self._store.create_conversation(conversation)
            except ConcurrentWriteError:
                existing = await self._store.get_conversation(conversation_id)
        if existing is None or existing.owner != principal:
            raise ApplicationError(
                ApplicationErrorKind.FORBIDDEN,
                "Conversation is owned by a different principal.",
            )

    async def _resolve_turn_attachments(
        self,
        command: AgentTurnCommand,
        principal: PrincipalRef,
    ) -> tuple[AttachmentRef, ...]:
        if not command.attachment_ids:
            return ()
        if len(command.attachment_ids) > self._max_images_per_message:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Too many images in one message.",
            )
        attachments = await self._store.list_active_attachments(
            principal,
            conversation_id=self._conversation_id(command),
            request_id=command.request_id,
            attachment_ids=command.attachment_ids,
        )
        if len(attachments) != len(command.attachment_ids):
            raise ApplicationError(
                ApplicationErrorKind.NOT_FOUND,
                "One or more attachments do not exist for this message.",
            )
        return tuple(
            AttachmentRef(
                attachment_id=value.attachment_id,
                resource_key=value.resource_key,
                original_name=value.original_name,
                mime_type=value.mime_type,
                size_bytes=value.size_bytes,
            )
            for value in attachments
        )

    def _require_media(self) -> ZhizhiChatMediaStore:
        if self._media is None:
            raise ApplicationError(
                ApplicationErrorKind.UNAVAILABLE,
                "Image media storage is not configured.",
            )
        return self._media
