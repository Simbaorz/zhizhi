import json

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from zhizhi_platform.iam.passwords import hash_password
from zhizhi_portal_api.app import create_app
from zhizhi_portal_api.settings import PortalSettings


class TestPasswords:
    async def decrypt_async(self, value):
        return value

    def public_key_payload(self):
        return {"algorithm": "RSA-OAEP-256", "key_id": "test-only", "public_key_pem": "test-only"}


@pytest.fixture
async def gateway(tmp_path):
    platform = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/platform.db")
    portal = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/portal.db")
    async with platform.begin() as db:
        await db.execute(
            text(
                "CREATE TABLE zhizhi_tenant (id TEXT,tenant_code TEXT,tenant_name TEXT,status TEXT)"
            )
        )
        await db.execute(
            text(
                "INSERT INTO zhizhi_tenant VALUES ('t1','DEMO','Demo','active'),('t2','OTHER','Other','active')"
            )
        )
        await db.execute(
            text(
                "CREATE TABLE zhizhi_organization_unit (id TEXT,tenant_id TEXT,parent_id TEXT,name TEXT,sort_order INTEGER,status TEXT)"
            )
        )
        await db.execute(
            text(
                "INSERT INTO zhizhi_organization_unit VALUES ('division','t1',NULL,'Division',0,'active'),('team','t1','division','Team',0,'active'),('squad','t1','team','Squad',0,'active'),('foreign','t2',NULL,'Foreign',0,'active')"
            )
        )
        await db.execute(
            text(
                "CREATE TABLE zhizhi_admin_user (id TEXT,username TEXT,normalized_username TEXT,display_name TEXT,email TEXT,password_hash TEXT,token_version INTEGER,is_super INTEGER,status TEXT)"
            )
        )
        await db.execute(
            text(
                "INSERT INTO zhizhi_admin_user VALUES ('admin','admin','ADMIN','Admin','',:password,0,1,'active'),('ordinary','ordinary','ORDINARY','Ordinary','',:password,0,0,'active')"
            ),
            {"password": hash_password("test-password-123")},
        )
    calls = []

    def upstream(request):
        calls.append(request)
        if request.url.path.endswith("/stream"):
            return httpx.Response(
                200,
                content=b"event: done\ndata: {}\n\n",
                headers={"content-type": "text/event-stream"},
            )
        if request.url.path.endswith("skills") or request.url.path.endswith("scenes"):
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, json={"ok": True})

    http = httpx.AsyncClient(base_url="http://agent.test", transport=httpx.MockTransport(upstream))
    app = create_app(
        settings=PortalSettings(cookie_secure=False),
        platform_engine=platform,
        portal_engine=portal,
        password_transport=TestPasswords(),
        http_client=http,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://portal.test"
        ) as client:
            yield client, platform, calls
    await http.aclose()


async def login(client, username="admin", admin=True):
    prefix = "/api/admin/auth" if admin else "/api/auth"
    response = await client.post(
        prefix + "/login", json={"username": username, "encrypted_password": "test-password-123"}
    )
    assert response.status_code == 200, response.text
    csrf = client.cookies.get(f"zhizhi_portal_{'admin' if admin else 'user'}_csrf")
    return {"x-csrf-token": csrf}


async def account(client, headers, username="demo"):
    response = await client.post(
        "/api/admin/accounts",
        headers=headers,
        json={
            "username": username,
            "display_name": username,
            "encrypted_password": "test-password-123",
            "scopes": [{"tenant_id": "t1", "organization_unit_id": ""}],
        },
    )
    assert response.status_code == 201, response.text
    assert "password_hash" not in response.json()
    return response.json()


async def test_login_csrf_and_platform_is_read_only(gateway):
    client, platform, _ = gateway
    assert (await client.get("/api/admin/accounts")).status_code == 401
    assert (
        await client.post(
            "/api/admin/auth/login",
            json={"username": "ordinary", "encrypted_password": "test-password-123"},
        )
    ).status_code == 401
    headers = await login(client)
    assert (
        await client.post("/api/admin/accounts", json={"display_name": "Demo"})
    ).status_code == 403
    created = await account(client, headers)
    async with platform.connect() as db:
        tables = (
            await db.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'portal_%'")
            )
        ).all()
        assert tables == []
        await db.execute(text("UPDATE zhizhi_admin_user SET token_version=1 WHERE id='admin'"))
        await db.commit()
    assert (await client.get("/api/admin/accounts")).status_code == 401
    assert created["scopes"][0]["organization_unit_id"] == ""


async def test_root_and_arbitrary_depth_scopes(gateway):
    client, _, _ = gateway
    await login(client)
    response = await client.get("/api/admin/organization/tenants/t1/scopes")
    scopes = response.json()
    assert scopes[0]["organization_unit_id"] == ""
    assert next(item for item in scopes if item["organization_unit_id"] == "squad")[
        "organization_path"
    ] == ["Division", "Team", "Squad"]
    assert all(item["organization_unit_id"] != "foreign" for item in scopes)


async def test_server_injects_context_and_forbids_spoofed_identity(gateway):
    client, _, calls = gateway
    admin_headers = await login(client)
    created = await account(client, admin_headers)
    user_headers = await login(client, "demo", False)
    conversation = (
        await client.post(
            "/api/conversations",
            headers=user_headers,
            json={"scope_id": created["scopes"][0]["id"]},
        )
    ).json()
    id = conversation["id"]
    response = await client.get(
        f"/api/conversations/{id}/capabilities",
        params={"tenant_code": "OTHER", "principal_id": "admin"},
    )
    assert response.status_code == 200
    assert dict(calls[-1].url.params)["tenant_code"] == "DEMO"
    assert dict(calls[-1].url.params)["principal_id"] == created["id"]
    bad = await client.post(
        f"/api/conversations/{id}/chat/stream",
        headers=user_headers,
        json={"content": "Hello", "request_id": "r1", "principal_id": "other"},
    )
    assert bad.status_code == 422
    good = await client.post(
        f"/api/conversations/{id}/chat/stream",
        headers=user_headers,
        json={"content": "Hello", "request_id": "r1"},
    )
    assert good.status_code == 200
    assert json.loads(calls[-1].content)["principal_id"] == created["id"]
    directory = (await client.get("/api/conversations")).json()
    assert directory["items"][0]["title"] == "Hello"
    patch = await client.patch(
        f"/api/conversations/{id}", headers=user_headers, json={"archived": True}
    )
    assert patch.status_code == 200
    assert (
        await client.post(
            f"/api/conversations/{id}/chat/stream",
            headers=user_headers,
            json={"content": "Hello", "request_id": "r2"},
        )
    ).status_code == 409


async def test_revoke_scope_and_password_reset_revoke_access(gateway):
    client, _, _ = gateway
    admin_headers = await login(client)
    created = await account(client, admin_headers)
    user_headers = await login(client, "demo", False)
    conversation = (
        await client.post(
            "/api/conversations",
            headers=user_headers,
            json={"scope_id": created["scopes"][0]["id"]},
        )
    ).json()
    await client.patch(
        "/api/admin/accounts/" + created["id"],
        headers=admin_headers,
        json={"display_name": "Demo", "scopes": []},
    )
    assert (
        await client.get("/api/conversations/" + conversation["id"] + "/messages")
    ).status_code == 403
    await client.patch(
        "/api/admin/accounts/" + created["id"],
        headers=admin_headers,
        json={"display_name": "Demo", "encrypted_password": "another-password-123", "scopes": []},
    )
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_users_cannot_access_other_users_conversations(gateway):
    client, _, _ = gateway
    headers = await login(client)
    first = await account(client, headers)
    await account(client, headers, "second")
    user_headers = await login(client, "demo", False)
    convo = (
        await client.post(
            "/api/conversations", headers=user_headers, json={"scope_id": first["scopes"][0]["id"]}
        )
    ).json()
    await login(client, "second", False)
    assert (await client.get("/api/conversations/" + convo["id"] + "/messages")).status_code == 404
    assert (
        await client.post(
            "/api/conversations",
            headers={"x-csrf-token": client.cookies.get("zhizhi_portal_user_csrf")},
            json={"scope_id": first["scopes"][0]["id"]},
        )
    ).status_code == 403


async def test_login_attempts_are_bounded(gateway):
    client, _, _ = gateway
    for _ in range(5):
        assert (
            await client.post(
                "/api/auth/login", json={"username": "missing", "encrypted_password": "wrong"}
            )
        ).status_code == 401
    assert (
        await client.post(
            "/api/auth/login", json={"username": "missing", "encrypted_password": "wrong"}
        )
    ).status_code == 429
