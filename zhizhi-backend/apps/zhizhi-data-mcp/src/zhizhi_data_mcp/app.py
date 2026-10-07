"""MCP process startup with shared platform config storage and isolated business pools."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import Field
from starlette.applications import Starlette
from starlette.types import Receive, Scope, Send

from gewu_core import StorageEncryptionSettings
from gewu_core.config import SettingsModel, load_bootstrap_settings_as, load_settings
from gewu_core.database import DatabaseRuntime
from zhizhi_data_mcp.server import create_server_app
from zhizhi_platform import ZhizhiBootstrapSettings, ZhizhiDatabaseSettings
from zhizhi_platform.data_source.query import DataQueryService
from zhizhi_platform.data_source.repository import DataSourceRepository
from zhizhi_platform.data_source.settings import DataMcpServerSettings
from zhizhi_platform.iam.adapters.mysql import MysqlAdminOrgReadRepository


class DataMcpBootstrapSettings(ZhizhiBootstrapSettings):
    config_file: Path = Field(default=Path("conf/data-mcp.yml"), alias="CONFIG_FILE")


class DataMcpProcessSettings(SettingsModel):
    db: ZhizhiDatabaseSettings = Field(default_factory=ZhizhiDatabaseSettings)
    storage_encryption: StorageEncryptionSettings = Field(default_factory=StorageEncryptionSettings)
    data_mcp: DataMcpServerSettings = Field(default_factory=DataMcpServerSettings)


def create_app() -> Starlette:
    bootstrap = load_bootstrap_settings_as(DataMcpBootstrapSettings)
    settings = load_settings(DataMcpProcessSettings, bootstrap)
    if not settings.data_mcp.enabled:
        raise ValueError("data_mcp.enabled must be true for the query service.")
    database = DatabaseRuntime(settings.db, bootstrap.project_home)
    # Sessions are obtained only after database.startup; the delegating lifespan builds the MCP app.
    inner: Starlette | None = None

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        nonlocal inner
        await database.startup()
        if database.sessions is None:
            raise RuntimeError("Platform configuration database is unavailable.")
        repository = DataSourceRepository(database.sessions)
        queries = DataQueryService(repository, settings.data_mcp, settings.storage_encryption.key)
        inner = create_server_app(
            repository, MysqlAdminOrgReadRepository(database.sessions), queries, settings.data_mcp
        )
        try:
            async with inner.router.lifespan_context(inner):
                yield None
        finally:
            await database.shutdown()

    app = Starlette(lifespan=lifespan)

    async def dispatch(scope: Scope, receive: Receive, send: Send) -> None:
        if inner is None:
            raise RuntimeError("MCP service has not started.")
        await inner(scope, receive, send)

    from starlette.routing import Mount

    app.routes.append(Mount("/", app=dispatch))
    return app
