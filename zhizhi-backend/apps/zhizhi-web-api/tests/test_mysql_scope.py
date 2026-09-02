from sqlalchemy.ext.asyncio import create_async_engine

from zhizhi_web_api.mysql_scope import MysqlAgentScopeResolver


async def test_resolves_an_active_arbitrary_depth_organization_path() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            "CREATE TABLE zhizhi_tenant (id TEXT, tenant_code TEXT, normalized_tenant_code TEXT, "
            "storage_key TEXT, status TEXT)"
        )
        await connection.exec_driver_sql(
            "CREATE TABLE zhizhi_organization_unit (id TEXT, tenant_id TEXT, parent_id TEXT, "
            "external_key TEXT, storage_key TEXT, name TEXT, unit_type TEXT, status TEXT)"
        )
        await connection.exec_driver_sql(
            "INSERT INTO zhizhi_tenant VALUES ('t1','TP001','TP001','TP001','active')"
        )
        await connection.exec_driver_sql(
            "INSERT INTO zhizhi_organization_unit VALUES "
            "('division','t1',NULL,'division','DIVISION','Division','division','active'),"
            "('region','t1','division','north','NORTH','North','region','active'),"
            "('team','t1','region','platform','PLATFORM','Platform','team','active'),"
            "('squad','t1','team','runtime','RUNTIME','Runtime','squad','active')"
        )

    resolver = MysqlAgentScopeResolver(engine)
    scope = await resolver.resolve(
        tenant_id="t1",
        active_organization_unit_id="squad",
        principal_id="user-1",
        principal_type="user",
    )

    assert scope is not None
    assert scope.tenant_id == "t1"
    assert [unit.id for unit in scope.organization_path] == [
        "division",
        "region",
        "team",
        "squad",
    ]
    assert scope.principal_id == "user-1"
    await engine.dispose()


async def test_rejects_cross_tenant_or_cyclic_organization_paths() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            "CREATE TABLE zhizhi_tenant (id TEXT, tenant_code TEXT, normalized_tenant_code TEXT, "
            "storage_key TEXT, status TEXT)"
        )
        await connection.exec_driver_sql(
            "CREATE TABLE zhizhi_organization_unit (id TEXT, tenant_id TEXT, parent_id TEXT, "
            "external_key TEXT, storage_key TEXT, name TEXT, unit_type TEXT, status TEXT)"
        )
        await connection.exec_driver_sql(
            "INSERT INTO zhizhi_tenant VALUES ('t1','TP001','TP001','TP001','active')"
        )
        await connection.exec_driver_sql(
            "INSERT INTO zhizhi_organization_unit VALUES "
            "('one','t1','two','one','ONE','One','team','active'),"
            "('two','t1','one','two','TWO','Two','team','active'),"
            "('foreign','t2',NULL,'foreign','FOREIGN','Foreign','team','active')"
        )

    resolver = MysqlAgentScopeResolver(engine)
    cyclic = await resolver.resolve(
        tenant_id="t1",
        active_organization_unit_id="one",
        principal_id="user-1",
        principal_type="user",
    )
    foreign = await resolver.resolve(
        tenant_id="t1",
        active_organization_unit_id="foreign",
        principal_id="user-1",
        principal_type="user",
    )

    assert cyclic is None
    assert foreign is None
    await engine.dispose()
