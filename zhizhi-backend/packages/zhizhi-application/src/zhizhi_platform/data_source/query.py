"""Read-only SQL validation and bounded execution owned by the data MCP service."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from contextlib import suppress
from typing import Any

import sqlglot
from pydantic_core import to_jsonable_python
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlglot import exp

from gewu_core import JsonSecretCipher
from zhizhi_platform.data_source.domain import DataSourceConfig
from zhizhi_platform.data_source.pools import DataSourcePools
from zhizhi_platform.data_source.repository import DataSourceRepository
from zhizhi_platform.data_source.settings import DataMcpServerSettings

logger = logging.getLogger(__name__)

_FORBIDDEN_FUNCTIONS = {
    "PG_SLEEP",
    "PG_READ_FILE",
    "PG_READ_BINARY_FILE",
    "PG_LS_DIR",
    "LO_IMPORT",
    "LO_EXPORT",
    "PG_TERMINATE_BACKEND",
    "PG_CANCEL_BACKEND",
    "DBLINK",
    "DBLINK_EXEC",
    "LOAD_FILE",
    "SLEEP",
    "BENCHMARK",
    "GET_LOCK",
    "RELEASE_LOCK",
    "NEXTVAL",
    "SETVAL",
    "SET_CONFIG",
}


def validate_query(
    sql: str,
    driver: str,
    allowed_schemas: tuple[str, ...],
    parameters: dict[str, Any],
    row_limit: int | None = None,
) -> str:
    if len(sql.encode()) > 65536:
        raise ValueError("SQL exceeds 64 KiB.")
    try:
        statements = sqlglot.parse(sql, read="postgres" if driver == "postgresql" else "mysql")
    except (sqlglot.errors.ParseError, sqlglot.errors.TokenError) as exc:
        raise ValueError("SQL cannot be parsed for this data source.") from exc
    if len(statements) != 1 or not isinstance(
        statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)
    ):
        raise ValueError("Only one read-only SELECT/WITH query is allowed.")
    statement = statements[0]
    forbidden = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Create,
        exp.Drop,
        exp.Alter,
        exp.Command,
        exp.Into,
        exp.Lock,
        exp.Transaction,
    )
    if any(isinstance(node, forbidden) for node in statement.walk()):
        raise ValueError("Mutations, SELECT INTO, and locking queries are not allowed.")
    for function in statement.find_all(exp.Func):
        name = function.name if isinstance(function, exp.Anonymous) else function.sql_name()
        if name.upper() in _FORBIDDEN_FUNCTIONS:
            raise ValueError("This SQL function is not permitted.")
    for table in statement.find_all(exp.Table):
        if table.catalog or (table.db and table.db not in allowed_schemas):
            raise ValueError("The query references a schema outside this source's allowlist.")
    required = set(text(sql).compile().params)
    if required != set(parameters):
        raise ValueError("SQL parameters must exactly match the named placeholders.")
    if len(json.dumps(parameters, default=str).encode()) > 16384:
        raise ValueError("SQL parameters exceed 16 KiB.")
    normalized = sql.strip().rstrip(";")
    if row_limit is not None:
        limit = statement.args.get("limit")
        if limit is None:
            normalized += f"\nLIMIT {row_limit}"
        else:
            value = limit.expression
            count: object
            if isinstance(value, exp.Literal) and value.is_int:
                count = int(value.this)
            elif isinstance(value, exp.Placeholder):
                count = parameters.get(value.name)
            else:
                raise ValueError("LIMIT must be an integer or named integer parameter.")
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
                or count > row_limit
            ):
                raise ValueError("LIMIT exceeds the source's maximum result rows.")
    return normalized


class DataQueryService:
    def __init__(
        self, repository: DataSourceRepository, settings: DataMcpServerSettings, encryption_key: str
    ) -> None:
        self.repository = repository
        self.settings = settings
        self._key = encryption_key
        self.pools = DataSourcePools(self._engine, settings)
        self._maintenance: asyncio.Task[None] | None = None
        self._queries: set[asyncio.Task[Any]] = set()
        self._closing = False

    def _engine(self, source: DataSourceConfig) -> AsyncEngine:
        password = JsonSecretCipher(self._key).decrypt(source.credentials_ciphertext)["password"]
        driver = "mysql+asyncmy" if source.driver == "mysql" else "postgresql+asyncpg"
        args: dict[str, Any] = {
            (
                "connect_timeout" if source.driver == "mysql" else "timeout"
            ): source.connect_timeout_seconds
        }
        if source.tls:
            args["ssl"] = ssl.create_default_context()
        return create_async_engine(
            URL.create(
                driver,
                username=source.username,
                password=password,
                host=source.host,
                port=source.port,
                database=source.database,
            ),
            pool_size=source.pool_size,
            max_overflow=0,
            pool_timeout=source.pool_timeout_seconds,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args=args,
            hide_parameters=True,
        )

    async def start(self) -> None:
        # Fail startup if configuration storage is unavailable, without connecting to business DBs.
        await self.repository.list_sources(page_size=1)
        self._maintenance = asyncio.create_task(self._maintain())

    async def _maintain(self) -> None:
        while True:
            await asyncio.sleep(min(30, self.settings.idle_pool_seconds))
            try:
                for source_id in self.pools.source_ids:
                    source = await self.repository.get_source(source_id)
                    await self.pools.retire(
                        source_id,
                        (
                            source.connection_revision
                            if source
                            and source.status == "active"
                            and source.server_id == self.settings.server_id
                            else None
                        ),
                    )
                await self.pools.reap()
            except Exception as exc:
                # Execution still rereads authoritative config before every query.
                logger.warning("Data pool maintenance failed error_type=%s", type(exc).__name__)
                continue

    async def execute(
        self, source: DataSourceConfig, sql: str, parameters: dict[str, Any], purpose: str
    ) -> dict[str, Any]:
        if (
            self._closing
            or source.status != "active"
            or source.server_id != self.settings.server_id
        ):
            raise ValueError("Data source is unavailable on this MCP server.")
        schemas = source.allowed_schemas or (
            (source.database,) if source.driver == "mysql" else ("public",)
        )
        validated = validate_query(sql, source.driver, schemas, parameters, source.max_rows + 1)
        task = asyncio.current_task()
        assert task is not None
        self._queries.add(task)
        try:
            async with asyncio.timeout(source.query_timeout_seconds):
                async with self.pools.lease(source) as engine:
                    async with engine.connect() as connection:
                        try:
                            if engine.dialect.name == "mysql":
                                await connection.exec_driver_sql(
                                    "SET SESSION TRANSACTION READ ONLY"
                                )
                                await connection.exec_driver_sql(
                                    f"SET SESSION max_execution_time = {int(source.query_timeout_seconds * 1000)}"
                                )
                                await connection.commit()
                            async with connection.begin():
                                if engine.dialect.name == "postgresql":
                                    await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                                    await connection.execute(
                                        text("SELECT set_config('statement_timeout', :ms, true)"),
                                        {"ms": str(int(source.query_timeout_seconds * 1000))},
                                    )
                                    await connection.execute(
                                        text("SELECT set_config('search_path', :schemas, true)"),
                                        {
                                            "schemas": ", ".join(
                                                '"' + schema.replace('"', '""') + '"'
                                                for schema in schemas
                                            )
                                        },
                                    )
                                elif engine.dialect.name == "sqlite":
                                    await connection.exec_driver_sql("PRAGMA query_only=ON")
                                result = await connection.stream(text(validated), parameters)
                                columns = list(result.keys())
                                rows: list[dict[str, Any]] = []
                                truncated = False
                                metadata = {
                                    "columns": columns,
                                    "rows": [],
                                    "row_count": 0,
                                    "truncated": True,
                                    "data_source_tag": source.tag,
                                    "purpose": purpose,
                                }
                                used_bytes = (
                                    len(json.dumps(metadata, ensure_ascii=False).encode()) + 32
                                )
                                try:
                                    async for row in result.mappings():
                                        if len(rows) >= source.max_rows:
                                            truncated = True
                                            break
                                        candidate = to_jsonable_python(dict(row), fallback=str)
                                        row_bytes = (
                                            len(json.dumps(candidate, ensure_ascii=False).encode())
                                            + 2
                                        )
                                        if used_bytes + row_bytes > source.max_result_bytes:
                                            truncated = True
                                            break
                                        rows.append(candidate)
                                        used_bytes += row_bytes
                                finally:
                                    await result.close()
                                payload = {
                                    "columns": columns,
                                    "rows": rows,
                                    "row_count": len(rows),
                                    "truncated": truncated,
                                    "data_source_tag": source.tag,
                                    "purpose": purpose,
                                }
                                if (
                                    len(json.dumps(payload, ensure_ascii=False).encode())
                                    > source.max_result_bytes
                                ):
                                    raise ValueError(
                                        "Result metadata exceeds the configured byte limit."
                                    )
                                return payload
                        except BaseException:
                            # Unknown/cancelled driver state must never return to the pool.
                            with suppress(Exception):
                                await asyncio.shield(connection.invalidate())
                            raise
        finally:
            self._queries.discard(task)

    async def close(self) -> None:
        self._closing = True
        if self._maintenance:
            self._maintenance.cancel()
            with suppress(asyncio.CancelledError):
                await self._maintenance
        tasks = tuple(self._queries)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=self.settings.shutdown_timeout_seconds)
        await self.pools.close()
