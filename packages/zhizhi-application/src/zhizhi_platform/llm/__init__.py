"""Zhizhi-specific managed model package."""

from zhizhi_platform.llm.connectivity import ProviderConnectivityTester
from zhizhi_platform.llm.credentials import ConfiguredLLMCredentialCipher
from zhizhi_platform.llm.domain import (
    ManagedLLMBinding,
    ManagedLLMConfig,
    ManagedLLMEntitlement,
)
from zhizhi_platform.llm.policy import safe_error_message, validate_llm_endpoint_url
from zhizhi_platform.llm.service import (
    CreateLLMBindingCommand,
    CreateLLMConfigCommand,
    CreateLLMEntitlementCommand,
    CreateLLMEntitlementsCommand,
    UpdateLLMBindingCommand,
    UpdateLLMConfigCommand,
    ZhizhiLLMAdminService,
)
from zhizhi_platform.llm.settings import OutboundHttpSettings

__all__ = [
    "ConfiguredLLMCredentialCipher",
    "CreateLLMBindingCommand",
    "CreateLLMConfigCommand",
    "CreateLLMEntitlementCommand",
    "CreateLLMEntitlementsCommand",
    "ZhizhiLLMAdminService",
    "ManagedLLMBinding",
    "ManagedLLMConfig",
    "ManagedLLMEntitlement",
    "OutboundHttpSettings",
    "ProviderConnectivityTester",
    "UpdateLLMBindingCommand",
    "UpdateLLMConfigCommand",
    "safe_error_message",
    "validate_llm_endpoint_url",
]
