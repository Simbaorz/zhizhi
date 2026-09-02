from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from gewu_agent_runtime.adapters.mysql import AgentRuntimeBase
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.schema import ensure_schema


async def _table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))


async def test_enabled_schema_creation_contains_all_application_and_runtime_tables() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        await ensure_schema(engine, auto_create=True)

        assert await _table_names(engine) == {
            *ZhizhiBase.metadata.tables,
            *AgentRuntimeBase.metadata.tables,
        }
    finally:
        await engine.dispose()


async def test_disabled_schema_creation_leaves_the_database_unchanged() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        await ensure_schema(engine, auto_create=False)

        assert await _table_names(engine) == set()
    finally:
        await engine.dispose()


async def test_existing_schema_is_not_created_again() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    statements: list[str] = []
    try:
        await ensure_schema(engine, auto_create=True)
        event.listen(
            engine.sync_engine,
            "before_cursor_execute",
            lambda _conn, _cursor, statement, _parameters, _context, _executemany: (
                statements.append(statement)
            ),
        )

        await ensure_schema(engine, auto_create=True)

        assert not any(
            statement.lstrip().upper().startswith("CREATE TABLE") for statement in statements
        )
    finally:
        await engine.dispose()


def test_application_tables_use_zhizhi_prefix() -> None:
    assert ZhizhiBase.metadata.tables
    assert all(name.startswith("zhizhi_") for name in ZhizhiBase.metadata.tables)
