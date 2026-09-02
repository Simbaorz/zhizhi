"""Read-only Slash candidate contracts."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from zhizhi.contracts import AgentContext


class SlashCandidate(BaseModel):
    """One scope-resolved Scene or Skill exposed to the host UI."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["scene", "skill"]
    asset_key: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


class SlashCatalog(Protocol):
    """List assets after subscriber hierarchy and visibility resolution."""

    async def list_skills(self, context: AgentContext) -> tuple[SlashCandidate, ...]: ...

    async def list_scenes(self, context: AgentContext) -> tuple[SlashCandidate, ...]: ...
