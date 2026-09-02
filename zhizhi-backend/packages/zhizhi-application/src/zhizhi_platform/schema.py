"""Explicit policy for ensuring the complete relational schema."""

from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.schema import MetaData

from gewu_agent_runtime.adapters.mysql import AgentRuntimeBase
from zhizhi import assets as _assets
from zhizhi_platform.audit import mysql as _audit_mysql
from zhizhi_platform.data_source.adapters.mysql import models as _business_models
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.git.adapters.mysql import models as _git_models
from zhizhi_platform.iam.adapters.mysql import models as _iam_models
from zhizhi_platform.llm.adapters.mysql import models as _llm_models
from zhizhi_platform.workspace.adapters.mysql import models as _workspace_models

_MODEL_MODULES = (
    _assets,
    _audit_mysql,
    _business_models,
    _git_models,
    _iam_models,
    _llm_models,
    _workspace_models,
)


def _create_missing_tables(connection: Connection, metadata: MetaData) -> None:
    existing_tables = set(inspect(connection).get_table_names())
    missing_tables = [
        table for table_name, table in metadata.tables.items() if table_name not in existing_tables
    ]
    if missing_tables:
        metadata.create_all(connection, tables=missing_tables, checkfirst=True)


async def ensure_schema(engine: AsyncEngine, *, auto_create: bool) -> None:
    """Create missing subscriber and Agent Runtime tables when explicitly enabled."""

    if not auto_create:
        return
    async with engine.begin() as connection:
        await connection.run_sync(_create_missing_tables, ZhizhiBase.metadata)
        await connection.run_sync(_create_missing_tables, AgentRuntimeBase.metadata)
