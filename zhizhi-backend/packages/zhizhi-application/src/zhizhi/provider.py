"""致知 SubscriberRuntimeProvider implementation."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, SkipValidation

from gewu_agent_runtime import (
    AttachmentLoader,
    AttachmentRef,
    PreparedAgentTurn,
    PrincipalRef,
    PrincipalType,
    TurnBindings,
    TurnRequest,
)
from gewu_agent_runtime.builtins import SceneCatalog, SkillCatalog
from gewu_agent_runtime.invocation import InvocationTarget, InvocationTargetKind
from gewu_agent_runtime.llm import ChatModel
from gewu_agent_runtime.prompts import SystemPrompt
from gewu_agent_runtime.tools import Tool, ToolRuntimeBindings
from gewu_core.errors import ApplicationError, ApplicationErrorKind
from zhizhi.capabilities import (
    ReadOnlyWorkspaceBackends,
    build_read_only_tool_set,
    build_read_only_workspace,
)
from zhizhi.contracts import AgentContext, AgentTurnCommand
from zhizhi.conversations import runtime_conversation_id
from zhizhi.scope import AgentScope, AgentScopeResolver


class ResolvedTurnCapabilities(BaseModel):
    """Already-authorized 致知 capabilities for one turn."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    model: SkipValidation[ChatModel]
    prompt: SystemPrompt
    workspace_backends: ReadOnlyWorkspaceBackends
    data_source_tool: SkipValidation[Tool | None] = None
    skill_catalog: SkipValidation[SkillCatalog]
    scene_catalog: SkipValidation[SceneCatalog]
    tool_runtime: ToolRuntimeBindings = Field(default_factory=ToolRuntimeBindings)
    max_iterations: int = Field(default=50, ge=1)
    ask_timeout_seconds: int = Field(default=300, ge=1)


class TurnCapabilityResolver(Protocol):
    """Resolve management-configured capabilities for one validated scope."""

    async def resolve(self, scope: AgentScope) -> ResolvedTurnCapabilities: ...

    async def supports_vision(self, scope: AgentScope) -> bool: ...


class ZhizhiRuntimeProvider:
    """Prepare one complete, read-only Agent workbench turn."""

    def __init__(
        self,
        *,
        subscriber_id: str,
        scopes: AgentScopeResolver,
        capabilities: TurnCapabilityResolver,
        attachment_loader: AttachmentLoader | None = None,
    ) -> None:
        if not subscriber_id.strip():
            raise ValueError("subscriber_id is required")
        self.subscriber_id = subscriber_id.strip()
        self._scopes = scopes
        self._capabilities = capabilities
        self._attachment_loader = attachment_loader

    def principal_for(self, principal_id: str, principal_type: str = "user") -> PrincipalRef:
        return PrincipalRef(
            subscriber_id=self.subscriber_id,
            principal_id=principal_id.strip(),
            principal_type=PrincipalType(principal_type),
        )

    async def prepare_turn(
        self,
        principal: PrincipalRef,
        command: AgentTurnCommand,
        attachments: tuple[AttachmentRef, ...] = (),
    ) -> PreparedAgentTurn:
        expected = self.principal_for(command.principal_id, command.principal_type)
        if principal != expected:
            raise ApplicationError(
                ApplicationErrorKind.FORBIDDEN,
                "Turn principal does not match the caller principal.",
            )
        scope = await self.resolve_scope(command)
        request = TurnRequest(
            invoker=principal,
            owner=principal,
            content=command.content,
            attachments=attachments,
            conversation_id=self.conversation_id(command.conversation_id, command.principal_id),
            request_id=command.request_id,
            input_message_id=command.request_id,
            idempotency_key=command.request_id,
            conversation_title=command.conversation_id,
            metadata={
                **command.metadata,
                "zhizhi": {
                    "conversation_id": command.conversation_id,
                    "tenant_id": command.tenant_id,
                    "active_organization_unit_id": command.active_organization_unit_id,
                    "principal_id": command.principal_id,
                    "principal_type": command.principal_type,
                },
            },
            invocation_target=_invocation_target(command),
        )

        return PreparedAgentTurn(
            request=request,
            bindings_factory=lambda: self.prepare_bindings(scope),
        )

    def conversation_id(self, conversation_id: str, principal_id: str) -> str:
        return runtime_conversation_id(self.subscriber_id, conversation_id, principal_id)

    async def resolve_scope(self, command: AgentContext) -> AgentScope:
        scope = await self._scopes.resolve(
            tenant_id=command.tenant_id,
            active_organization_unit_id=command.active_organization_unit_id,
            principal_id=command.principal_id,
            principal_type=command.principal_type,
        )
        if scope is None:
            raise ApplicationError(
                ApplicationErrorKind.INVALID_INPUT,
                "Tenant or active organization unit is invalid or inactive.",
            )
        return scope

    async def supports_vision(self, command: AgentContext) -> bool:
        scope = await self.resolve_scope(command)
        return await self._capabilities.supports_vision(scope)

    async def prepare_bindings(self, scope: AgentScope) -> TurnBindings:
        resolved = await self._capabilities.resolve(scope)
        workspace = build_read_only_workspace(resolved.workspace_backends)
        return TurnBindings(
            model=resolved.model,
            workspace=workspace,
            tool_set=build_read_only_tool_set(
                resolved.data_source_tool,
                ask_timeout_seconds=resolved.ask_timeout_seconds,
            ),
            tool_runtime=resolved.tool_runtime,
            prompt=resolved.prompt,
            skill_catalog=resolved.skill_catalog,
            scene_catalog=resolved.scene_catalog,
            attachment_loader=self._attachment_loader,
            max_iterations=resolved.max_iterations,
        )


def _invocation_target(command: AgentTurnCommand) -> InvocationTarget | None:
    target = command.slash_target
    if target is None:
        return None
    kind = InvocationTargetKind(target.kind)
    return InvocationTarget(
        kind=kind,
        resource_id=target.asset_key,
        name=target.name,
        arguments=command.content.strip() if kind is InvocationTargetKind.SKILL else "",
    )
