"""Composition root for the Zhizhi Web API process."""

from __future__ import annotations

from typing import Any, cast

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gewu_agent_runtime import AgentRuntime, ImagePayloadManager, initialize_context_token_encodings
from gewu_agent_runtime.adapters.llm import DefaultProviderChatModelFactory
from gewu_agent_runtime.adapters.mysql import SqlAlchemyRuntimeStore
from gewu_agent_runtime.adapters.redis import RedisRunLease, RedisStateCache
from gewu_core import ConfiguredJsonSecretCipher
from gewu_core.apollo_config import load_settings_once
from gewu_core.config import (
    ApolloBootstrapSettings,
    BootstrapSettings,
    DeploymentMode,
    load_settings,
)
from gewu_core.database import DatabaseRuntime
from gewu_core.http import HttpInfrastructureRuntime
from gewu_core.redis import RedisClient
from zhizhi import (
    AgentWorkbenchService,
    MysqlSharedAssetRepository,
    ZhizhiRuntimeProvider,
)
from zhizhi.runtime_capabilities import ZhizhiCapabilityResolver
from zhizhi.shared_catalogs import SharedCatalogs
from zhizhi_platform import (
    ZhizhiDataSourceCapabilityBuilder,
    ZhizhiDataSourceSourceResolver,
    ZhizhiModelBindingResolver,
)
from zhizhi_platform.adapters import build_zhizhi_chat_media_store
from zhizhi_platform.adapters.filesystem import (
    ZhizhiFilesystemWorkspaceBackendFactory,
)
from zhizhi_platform.adapters.http import HttpDataSourceQueryGateway
from zhizhi_platform.adapters.mysql import (
    MysqlDataSourceRuntimeRepository,
    MysqlModelRuntimeRepository,
)
from zhizhi_platform.chat_media import ZhizhiChatMediaStore
from zhizhi_platform.data_source import ConfiguredDataSourceCredentialCipher
from zhizhi_platform.iam.adapters.mysql import MysqlOrganizationDirectory
from zhizhi_platform.llm import ConfiguredLLMCredentialCipher
from zhizhi_platform.llm.capability import ZhizhiModelCapabilityBuilder
from zhizhi_platform.schema import ensure_schema_for_mode
from zhizhi_web_api.mysql_scope import MysqlAgentScopeResolver
from zhizhi_web_api.settings import WebApiSettings
from zhizhi_web_api.slash_catalog import MysqlSlashCatalog

SUBSCRIBER_ID = "zhizhi"


class ZhizhiApiRuntime:
    """Own all process resources without initializing Zhizhi browser IAM."""

    def __init__(
        self,
        bootstrap: BootstrapSettings,
        *,
        settings: WebApiSettings | None = None,
    ) -> None:
        self.bootstrap = bootstrap
        self.settings = settings
        self._database: DatabaseRuntime | None = None
        self._http: HttpInfrastructureRuntime | None = None
        self._redis: RedisClient | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._model_factory: DefaultProviderChatModelFactory | None = None
        self._data_source_gateway: HttpDataSourceQueryGateway | None = None
        self._agent_runtime: AgentRuntime | None = None
        self._media_store: ZhizhiChatMediaStore | None = None
        self.service: AgentWorkbenchService | None = None
        self.catalog: MysqlSlashCatalog | None = None
        self._started = False

    async def startup(self) -> None:
        if self._started:
            return
        settings = self.settings
        if settings is None:
            if isinstance(self.bootstrap, ApolloBootstrapSettings):
                settings = await load_settings_once(
                    WebApiSettings,
                    self.bootstrap,
                    required_paths=("redis.connection", "workspace.storage_root"),
                )
            else:
                settings = load_settings(
                    WebApiSettings,
                    self.bootstrap,
                    required_paths=("redis.connection", "workspace.storage_root"),
                )
        self.settings = settings
        try:
            await self._startup_components(settings)
        except BaseException:
            await self.shutdown()
            raise

    async def _startup_components(self, settings: WebApiSettings) -> None:
        """Build process resources after settings have been resolved."""

        self._http = HttpInfrastructureRuntime(self.bootstrap, settings=settings)
        await self._http.startup()  # noqa
        await initialize_context_token_encodings(
            require_complete_cache=self.bootstrap.mode is DeploymentMode.PROD
        )
        self._database = DatabaseRuntime(settings.db, self.bootstrap.project_home)
        await self._database.startup()  # noqa
        engine = self._database.engine  # noqa
        sessions = self._database.sessions  # noqa
        if engine is None or sessions is None:
            raise RuntimeError("Database dependencies were not initialized.")
        await ensure_schema_for_mode(engine, self.bootstrap.mode)

        self._redis = RedisClient(settings.redis)
        await self._redis.initialize()  # noqa
        self._compose(engine, sessions, settings)
        assert self._agent_runtime is not None
        self._agent_runtime.start()
        self._started = True

    def _compose(
        self,
        engine: Any,
        sessions: async_sessionmaker[AsyncSession],
        settings: WebApiSettings,
    ) -> None:
        workspace_backends = ZhizhiFilesystemWorkspaceBackendFactory(
            settings.workspace.storage_root,
            max_file_bytes=settings.workspace.max_file_bytes,
        )
        self._http_client = _build_http_client(settings)
        self._model_factory = DefaultProviderChatModelFactory(http_client=self._http_client)
        organization_directory = MysqlOrganizationDirectory(sessions)
        model_repository = MysqlModelRuntimeRepository(sessions, organization_directory)
        model_resolver = ZhizhiModelBindingResolver(
            model_repository,
            ZhizhiModelCapabilityBuilder(
                model_repository,
                self._model_factory,  # noqa
                ConfiguredLLMCredentialCipher(settings.storage_encryption.key),
            ),
        )
        self._data_source_gateway = HttpDataSourceQueryGateway(
            max_response_bytes=settings.data_source.max_response_bytes,
            client=self._http_client,
        )
        business_repository = MysqlDataSourceRuntimeRepository(sessions)
        business_resolver = ZhizhiDataSourceSourceResolver(
            business_repository,
            ZhizhiDataSourceCapabilityBuilder(
                business_repository,
                self._data_source_gateway,  # noqa
                ConfiguredDataSourceCredentialCipher(settings.storage_encryption.key),
            ),
        )
        shared_assets = MysqlSharedAssetRepository(sessions)
        catalog_resolver = SharedCatalogs(shared_assets, workspace_backends)
        store = SqlAlchemyRuntimeStore(
            sessions,
            protected_payload_cipher=ConfiguredJsonSecretCipher(
                settings.storage_encryption.key,
                setting_name="storage_encryption.key",
            ),
            encrypt_protected_payloads=settings.agent.encrypt_tool_results,
            encrypt_compactions=settings.agent.encrypt_compaction_summaries,
        )
        if self._redis is None:
            raise RuntimeError("Redis was not initialized.")
        redis_connection = cast(Any, self._redis.connection)
        prefix = f"{self.bootstrap.project_name}:{self.bootstrap.mode.value}:web-agent"
        self._agent_runtime = AgentRuntime(
            store=store,
            run_lease=RedisRunLease(
                redis_connection,
                key_prefix=prefix,
                ttl_seconds=settings.agent.run_lease_ttl_seconds,
            ),
            state_cache=RedisStateCache(
                redis_connection,
                key_prefix=f"{prefix}:state",
                default_ttl_seconds=settings.agent.state_cache_ttl_seconds,
            ),
            image_payload_manager=ImagePayloadManager(
                raw_capacity_bytes=settings.agent.image_raw_in_flight_bytes,
                encoded_capacity_bytes=settings.agent.image_encoded_in_flight_bytes,
                provider_payload_capacity_bytes=(
                    settings.agent.image_provider_payload_in_flight_bytes
                ),
                admission_timeout_seconds=settings.agent.image_admission_timeout_seconds,
            ),
            micro_compact_keep_recent_tool_results=(
                settings.agent.micro_compact_keep_recent_tool_results
            ),
            max_concurrent_turns=settings.agent.max_concurrent_turns_per_process,
            queue_capacity=settings.agent.queue_capacity,
            admission_timeout_seconds=settings.agent.admission_timeout_seconds,
            pending_ask_cleanup_interval_seconds=(
                settings.agent.pending_ask_cleanup_interval_seconds
            ),
        )
        scopes = MysqlAgentScopeResolver(engine)
        self._media_store = build_zhizhi_chat_media_store(
            settings.media,
            self.bootstrap.project_home,
        )
        provider = ZhizhiRuntimeProvider(
            subscriber_id=SUBSCRIBER_ID,
            scopes=scopes,
            capabilities=ZhizhiCapabilityResolver(
                models=model_resolver,  # noqa
                data_source=business_resolver,  # noqa
                catalogs=catalog_resolver,
                workspace_backends=workspace_backends,
                max_iterations=settings.agent.max_iterations,
                ask_timeout_seconds=settings.agent.ask_user_timeout_seconds,
                data_source_max_result_bytes=settings.data_source.max_tool_result_bytes,
            ),
            attachment_loader=self._media_store,
        )
        self.service = AgentWorkbenchService(
            runtime=self._agent_runtime,  # noqa
            store=store,
            provider=provider,
            media=self._media_store,
            max_image_bytes=settings.media.max_image_bytes,
            max_images_per_message=settings.media.max_images_per_message,
        )
        self.catalog = MysqlSlashCatalog(
            scopes=scopes,
            assets=shared_assets,
        )

    async def shutdown(self) -> None:
        self._started = False
        self.service = None
        self.catalog = None
        agent_runtime = self._agent_runtime
        self._agent_runtime = None
        if agent_runtime is not None:
            await agent_runtime.stop()
        media_store = self._media_store
        self._media_store = None
        if media_store is not None:
            await media_store.close()
        if self._data_source_gateway is not None:
            await self._data_source_gateway.aclose()
            self._data_source_gateway = None
        if self._model_factory is not None:
            await self._model_factory.aclose()
            self._model_factory = None
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
        if self._database is not None:
            await self._database.shutdown()
            self._database = None
        if self._http is not None:
            await self._http.shutdown()
            self._http = None

    @property
    def ready(self) -> bool:
        return self._started and self.service is not None and self.catalog is not None


def _build_http_client(settings: WebApiSettings) -> httpx.AsyncClient:
    outbound = settings.outbound_http
    return httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=outbound.max_connections,
            max_keepalive_connections=outbound.max_keepalive_connections,
            keepalive_expiry=outbound.keepalive_expiry_seconds,
        ),
        timeout=httpx.Timeout(
            timeout=600.0,
            connect=outbound.connect_timeout_seconds,
            pool=outbound.pool_timeout_seconds,
        ),
    )
