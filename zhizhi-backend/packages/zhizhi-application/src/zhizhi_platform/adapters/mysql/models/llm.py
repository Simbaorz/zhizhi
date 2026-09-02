"""Compatibility exports for LLM rows owned by the 致知 LLM package."""

from zhizhi_platform.llm.adapters.mysql.models import (
    LLMBindingModel,
    LLMConfigModel,
    LLMEntitlementModel,
)

__all__ = ["LLMBindingModel", "LLMConfigModel", "LLMEntitlementModel"]
