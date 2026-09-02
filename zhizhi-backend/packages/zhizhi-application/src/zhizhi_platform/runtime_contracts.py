"""Minimal capability contracts used by the Agent runtime."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, SkipValidation

from gewu_agent_runtime.compaction import CompactionModel
from gewu_agent_runtime.llm import ChatModel
from gewu_agent_runtime.runtime import SafeExecutionError
from zhizhi_platform.data_source.tool import DataSourceCapability
from zhizhi_platform.iam.identity import AccessScope


class ZhizhiModelNotConfiguredError(SafeExecutionError):
    """No active model binding is available for the requested shared scope."""

    def __init__(self, message: str = "当前范围未配置可用模型。") -> None:
        super().__init__(code="model_not_configured", message=message)


class ZhizhiResolvedModel(BaseModel):
    """Main and compaction model selected by the shared hierarchy."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    model: SkipValidation[ChatModel]
    compaction_model: SkipValidation[CompactionModel]


class ZhizhiDataSourceBinding(BaseModel):
    """One Data Source capability resolved for the active organization scope."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    capability: SkipValidation[DataSourceCapability]
    database_key: str = ""
    row_limit: int = Field(default=50, ge=1)


class ZhizhiTurnModelResolver(Protocol):
    async def resolve(self, scope: AccessScope) -> ZhizhiResolvedModel | None: ...


class ZhizhiDataSourceResolver(Protocol):
    async def resolve(self, scope: AccessScope) -> ZhizhiDataSourceBinding | None: ...
