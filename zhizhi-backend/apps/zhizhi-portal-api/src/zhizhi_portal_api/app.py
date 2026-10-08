"""Optional test host: authenticated accounts, scoped directory and Agent gateway."""

import asyncio
import hashlib
import hmac
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from gewu_core.blocking import run_cpu_task
from gewu_core.config import load_bootstrap_settings_as, load_settings
from gewu_core.http import HttpRequestBodyLimitMiddleware
from gewu_core.http.password_transport import RsaPasswordTransport
from zhizhi.contracts import SlashTarget
from zhizhi_platform.iam.passwords import hash_password, verify_password
from zhizhi_portal_api.models import Account, Base, BrowserSession, Conversation, LoginAttempt
from zhizhi_portal_api.organization import OrganizationReader
from zhizhi_portal_api.settings import (
    PortalBootstrapSettings,
    PortalProcessSettings,
    PortalSettings,
    platform_infrastructure,
)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    username: str = Field(min_length=1, max_length=64)
    encrypted_password: str = Field(min_length=1, max_length=8192)


class ScopeBinding(Input):
    tenant_id: str = Field(min_length=1, max_length=64)
    organization_unit_id: str = Field(default="", max_length=64)


class AccountWrite(Input):
    username: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    email: str = Field(default="", max_length=320)
    encrypted_password: str | None = Field(default=None, max_length=8192)
    active: bool = True
    scopes: list[ScopeBinding] = Field(default_factory=list, max_length=100)


class NewConversation(Input):
    scope_id: str = Field(min_length=1, max_length=64)


class ConversationPatch(Input):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    archived: bool | None = None


class Chat(Input):
    content: str = Field(default="", max_length=65535)
    request_id: str = Field(min_length=1, max_length=64)
    attachment_ids: list[str] = Field(default_factory=list, max_length=16)
    slash_target: SlashTarget | None = None


class Ask(Input):
    request_id: str = Field(min_length=1, max_length=64)
    ask_id: str = Field(min_length=1, max_length=64)
    answers: dict[str, str | list[str]] = Field(default_factory=dict)
    status: str = Field(pattern="^(answered|skipped)$")


class PasswordChange(Input):
    encrypted_current_password: str = Field(min_length=1, max_length=8192)
    encrypted_new_password: str = Field(min_length=1, max_length=8192)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cookie_name(admin: bool, *, csrf: bool = False) -> str:
    return f"zhizhi_portal_{'admin' if admin else 'user'}_{'csrf' if csrf else 'session'}"


def conversation_public(row: Conversation) -> dict[str, Any]:
    return {
        "id": row.id,
        "scope_id": row.scope_id,
        "title": row.title,
        "archived": row.archived,
        "created_at": datetime.fromtimestamp(row.created_at, UTC).isoformat(),
        "updated_at": datetime.fromtimestamp(row.updated_at, UTC).isoformat(),
    }


def create_app(
    *,
    settings: PortalSettings | None = None,
    home: Path | None = None,
    platform_engine: AsyncEngine | None = None,
    portal_engine: AsyncEngine | None = None,
    password_transport: Any = None,
    http_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    if settings is None:
        bootstrap = load_bootstrap_settings_as(PortalBootstrapSettings)
        settings = load_settings(PortalProcessSettings, bootstrap).portal
        home = Path(bootstrap.project_home)
    root = (home or Path.cwd()).resolve()
    configuration = settings

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal platform_engine, portal_engine, password_transport, http_client
        if platform_engine is None:
            platform_engine, transport_settings = platform_infrastructure(configuration, root)
            password_transport = await RsaPasswordTransport.load(
                transport_settings, root, required=True
            )
        if portal_engine is None:
            file = (root / configuration.database_file).resolve()
            file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            file.touch(mode=0o600, exist_ok=True)
            file.chmod(0o600)
            portal_engine = create_async_engine(f"sqlite+aiosqlite:///{file}")
        if platform_engine.url == portal_engine.url:
            raise RuntimeError("Portal storage must use a separate database.")
        async with portal_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        app.state.sessions = async_sessionmaker(portal_engine, expire_on_commit=False)
        app.state.organization = OrganizationReader(platform_engine)
        app.state.password_transport = password_transport
        app.state.dummy_hash = await run_cpu_task(hash_password, secrets.token_urlsafe(32))
        owned_http = http_client is None
        http_client = http_client or httpx.AsyncClient(
            base_url=configuration.agent_api_url,
            timeout=httpx.Timeout(660, connect=5),
            follow_redirects=False,
        )
        app.state.http = http_client
        try:
            yield
        finally:
            if owned_http:
                await http_client.aclose()
            await portal_engine.dispose()
            await platform_engine.dispose()

    app = FastAPI(title="Zhizhi Test Portal", lifespan=lifespan)
    app.add_middleware(
        HttpRequestBodyLimitMiddleware,
        body_limit_resolver=lambda scope: (
            configuration.max_image_bytes + 65536
            if str(scope.get("path", "")).endswith("/attachments")
            else 256 * 1024
        ),
    )
    login_locks = [asyncio.Lock() for _ in range(64)]

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "请求参数无效，请检查表单。",
                "errors": [
                    {"loc": list(item["loc"]), "type": item["type"]} for item in error.errors()
                ],
            },
        )

    async def current(request: Request, *, admin: bool = False, mutate: bool = False) -> Any:
        raw = request.cookies.get(cookie_name(admin), "")
        async with app.state.sessions() as db:
            record = await db.get(BrowserSession, token_hash(raw)) if raw else None
            if record is None or record.admin != admin or record.expires_at <= time.time():
                raise HTTPException(401, "请先登录")
            principal = (
                await app.state.organization.admin(record.principal_id, by_id=True)
                if admin
                else await db.get(Account, record.principal_id)
            )
            version = (
                principal.get("token_version")
                if admin and principal
                else getattr(principal, "token_version", None)
            )
            if (
                principal is None
                or (not admin and not principal.active)
                or version != record.token_version
            ):
                raise HTTPException(401, "登录已失效，请重新登录")
            if mutate:
                cookie = request.cookies.get(cookie_name(admin, csrf=True), "")
                header = request.headers.get("x-csrf-token", "")
                if (
                    not cookie
                    or not header
                    or not hmac.compare_digest(cookie, record.csrf)
                    or not hmac.compare_digest(header, record.csrf)
                ):
                    raise HTTPException(403, "CSRF 校验失败")
            return principal

    def public_admin(principal: dict[str, Any]) -> dict[str, Any]:
        return {
            key: principal.get(key) or "" for key in ("id", "username", "display_name", "email")
        }

    async def decrypt(envelope: str, *, new: bool = False) -> str:
        try:
            password = await app.state.password_transport.decrypt_async(envelope)
        except ValueError as exc:
            raise HTTPException(400, "密码加密数据无效，请刷新页面重试") from exc
        if len(password) > 256 or (new and len(password) < 12):
            raise HTTPException(400, "新密码应为 12 至 256 位")
        return str(password)

    async def login(payload: Login, request: Request, response: Response, *, admin: bool) -> Any:
        username = payload.username.strip().casefold()
        attempt_key = token_hash(
            f"{request.client.host if request.client else ''}:{admin}:{username}"
        )
        async with login_locks[int(attempt_key[:2], 16) % 64]:
            async with app.state.sessions() as db:
                attempt = await db.get(LoginAttempt, attempt_key)
                if attempt and attempt.started_at + 600 > time.time() and attempt.failures >= 5:
                    raise HTTPException(429, "登录失败次数过多，请稍后再试")
                principal = (
                    await app.state.organization.admin(username)
                    if admin
                    else await db.scalar(select(Account).where(Account.username == username))
                )
                password = await decrypt(payload.encrypted_password)
                hashed = (
                    (principal["password_hash"] if admin else principal.password_hash)
                    if principal
                    else app.state.dummy_hash
                )
                valid = await run_cpu_task(verify_password, password, hashed)
                if principal is None or not valid or (not admin and not principal.active):
                    if not attempt:
                        attempt = LoginAttempt(key=attempt_key, failures=0, started_at=time.time())
                        db.add(attempt)
                    elif attempt.started_at + 600 <= time.time():
                        attempt.failures = 0
                        attempt.started_at = time.time()
                    attempt.failures += 1
                    await db.commit()
                    raise HTTPException(401, "用户名或密码错误")
                if attempt:
                    await db.delete(attempt)
                raw, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
                pid = principal["id"] if admin else principal.id
                version = principal["token_version"] if admin else principal.token_version
                db.add(
                    BrowserSession(
                        token_hash=token_hash(raw),
                        principal_id=pid,
                        admin=admin,
                        token_version=version,
                        csrf=csrf,
                        expires_at=time.time() + configuration.session_hours * 3600,
                    )
                )
                await db.commit()
            for name, value, private in (
                (cookie_name(admin), raw, True),
                (cookie_name(admin, csrf=True), csrf, False),
            ):
                response.set_cookie(
                    name,
                    value,
                    httponly=private,
                    secure=configuration.cookie_secure,
                    samesite="lax",
                    max_age=configuration.session_hours * 3600,
                    path="/",
                )
            return public_admin(principal) if admin else principal.public()

    async def owned(account: Account, id: str) -> Conversation:
        async with app.state.sessions() as db:
            row = await db.get(Conversation, id)
            if row is None or row.account_id != account.id:
                raise HTTPException(404, "会话不存在")
            return cast(Conversation, row)

    async def bound_scope(account: Account, id: str) -> dict[str, Any]:
        binding = next((item for item in account.scopes if item["id"] == id), None)
        if not binding:
            raise HTTPException(403, "未授权的业务范围")
        scope = await app.state.organization.scope(
            binding["tenant_id"], binding["organization_unit_id"]
        )
        if scope is None:
            raise HTTPException(403, "租户或组织已失效")
        return cast(dict[str, Any], scope)

    async def context(account: Account, id: str, *, write: bool = False) -> dict[str, str]:
        conversation = await owned(account, id)
        if write and conversation.archived:
            raise HTTPException(409, "请先恢复已归档会话")
        scope = await bound_scope(account, conversation.scope_id)
        return {
            "conversation_id": conversation.id,
            "tenant_code": scope["tenant_code"],
            "active_organization_unit_id": scope["organization_unit_id"],
            "principal_id": account.id,
            "principal_type": "user",
        }

    async def forward(
        method: str,
        path: str,
        *,
        query: Any = None,
        body: Any = None,
        files: Any = None,
        data: Any = None,
        stream: bool = False,
    ) -> Response:
        try:
            request = app.state.http.build_request(
                method, path, params=query, json=body, files=files, data=data
            )
            result = await app.state.http.send(request, stream=stream)
        except httpx.RequestError as exc:
            raise HTTPException(502, "Agent 服务暂时不可用") from exc
        if not stream or result.status_code >= 400:
            content = await result.aread()
            await result.aclose()
            return Response(
                content,
                status_code=result.status_code,
                media_type=result.headers.get("content-type", "application/json"),
            )

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in result.aiter_bytes():
                    yield chunk
            finally:
                await result.aclose()

        return StreamingResponse(
            chunks(),
            media_type=result.headers.get("content-type", "application/octet-stream"),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/healthz")
    async def health() -> Any:
        return {"status": "ok"}

    @app.get("/readyz")
    async def ready() -> Any:
        try:
            await app.state.organization.tenants()
            async with app.state.sessions() as db:
                await db.execute(select(Account.id).limit(1))
        except Exception as exc:
            raise HTTPException(503, "Portal 依赖暂时不可用") from exc
        return {"status": "ready"}

    @app.get("/api/auth/password-key")
    @app.get("/api/admin/auth/password-key")
    async def key() -> Any:
        return app.state.password_transport.public_key_payload()

    @app.post("/api/auth/login")
    async def user_login(payload: Login, request: Request, response: Response) -> Any:
        return await login(payload, request, response, admin=False)

    @app.post("/api/admin/auth/login")
    async def admin_login(payload: Login, request: Request, response: Response) -> Any:
        return await login(payload, request, response, admin=True)

    @app.get("/api/auth/me")
    async def me(request: Request) -> Any:
        return (await current(request)).public()

    @app.get("/api/admin/auth/me")
    async def admin_me(request: Request) -> Any:
        return public_admin(await current(request, admin=True))

    async def logout(request: Request, response: Response, *, admin: bool) -> Any:
        await current(request, admin=admin, mutate=True)
        async with app.state.sessions() as db:
            row = await db.get(BrowserSession, token_hash(request.cookies[cookie_name(admin)]))
            if row:
                await db.delete(row)
                await db.commit()
        response.delete_cookie(cookie_name(admin), path="/")
        response.delete_cookie(cookie_name(admin, csrf=True), path="/")
        return {"ok": True}

    @app.post("/api/auth/logout")
    async def user_logout(request: Request, response: Response) -> Any:
        return await logout(request, response, admin=False)

    @app.post("/api/admin/auth/logout")
    async def admin_logout(request: Request, response: Response) -> Any:
        return await logout(request, response, admin=True)

    @app.post("/api/auth/password")
    async def change_password(payload: PasswordChange, request: Request) -> Any:
        account = await current(request, mutate=True)
        if not await run_cpu_task(
            verify_password,
            await decrypt(payload.encrypted_current_password),
            account.password_hash,
        ):
            raise HTTPException(400, "当前密码不正确")
        password = await decrypt(payload.encrypted_new_password, new=True)
        async with app.state.sessions() as db:
            row = await db.get(Account, account.id)
            row.password_hash = await run_cpu_task(hash_password, password)
            row.token_version += 1
            await db.commit()
        return {"ok": True}

    @app.get("/api/admin/organization/tenants")
    async def tenants(request: Request) -> Any:
        await current(request, admin=True)
        return await app.state.organization.tenants()

    @app.get("/api/admin/organization/tenants/{id}/scopes")
    async def organization_scopes(id: str, request: Request) -> Any:
        await current(request, admin=True)
        return await app.state.organization.scopes(id)

    @app.get("/api/admin/accounts")
    async def accounts(request: Request) -> Any:
        await current(request, admin=True)
        async with app.state.sessions() as db:
            rows = (await db.scalars(select(Account).order_by(Account.username))).all()
            return [row.public(admin=True) for row in rows]

    async def write_account(payload: AccountWrite, request: Request, id: str | None = None) -> Any:
        await current(request, admin=True, mutate=True)
        pairs = [(item.tenant_id, item.organization_unit_id) for item in payload.scopes]
        if len(set(pairs)) != len(pairs):
            raise HTTPException(400, "授权范围不能重复")
        for tenant_id, organization_id in pairs:
            if await app.state.organization.scope(tenant_id, organization_id) is None:
                raise HTTPException(400, "租户或组织范围无效")
        password = (
            await decrypt(payload.encrypted_password, new=True)
            if payload.encrypted_password
            else None
        )
        async with app.state.sessions() as db:
            row = await db.get(Account, id) if id else None
            if id and row is None:
                raise HTTPException(404, "账号不存在")
            if row is None:
                if not payload.username or not password:
                    raise HTTPException(400, "请输入用户名和初始密码")
                row = Account(
                    id=uuid4().hex,
                    username=payload.username.casefold(),
                    display_name=payload.display_name,
                    scopes=[],
                    token_version=0,
                )
                db.add(row)
            elif payload.username and payload.username.casefold() != row.username:
                raise HTTPException(400, "用户名不可修改")
            existing = {
                (item["tenant_id"], item["organization_unit_id"]): item["id"] for item in row.scopes
            }
            row.scopes = [
                {
                    "id": existing.get(pair, uuid4().hex),
                    "tenant_id": pair[0],
                    "organization_unit_id": pair[1],
                }
                for pair in pairs
            ]
            row.display_name, row.email, row.active = (
                payload.display_name,
                payload.email,
                payload.active,
            )
            if password:
                row.password_hash = await run_cpu_task(hash_password, password)
                row.token_version += 1
            try:
                await db.commit()
            except IntegrityError as exc:
                await db.rollback()
                raise HTTPException(409, "用户名已存在") from exc
            return row.public(admin=True)

    @app.post("/api/admin/accounts", status_code=201)
    async def create_account(payload: AccountWrite, request: Request) -> Any:
        return await write_account(payload, request)

    @app.patch("/api/admin/accounts/{id}")
    async def update_account(id: str, payload: AccountWrite, request: Request) -> Any:
        return await write_account(payload, request, id)

    @app.get("/api/scopes")
    async def scopes(request: Request) -> Any:
        account = await current(request)
        result = []
        for binding in account.scopes:
            try:
                scope = await bound_scope(account, binding["id"])
            except HTTPException:
                continue
            result.append(
                {
                    "id": binding["id"],
                    "tenant_name": scope["tenant_name"],
                    "organization_path": scope["organization_path"],
                }
            )
        return result

    @app.get("/api/conversations")
    async def conversations(
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        archived: bool = False,
    ) -> Any:
        account = await current(request)
        async with app.state.sessions() as db:
            rows = (
                await db.scalars(
                    select(Conversation)
                    .where(Conversation.account_id == account.id, Conversation.archived == archived)
                    .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
                    .offset(offset)
                    .limit(limit + 1)
                )
            ).all()
            return {
                "items": [conversation_public(row) for row in rows[:limit]],
                "has_more": len(rows) > limit,
            }

    @app.post("/api/conversations", status_code=201)
    async def create_conversation(payload: NewConversation, request: Request) -> Any:
        account = await current(request, mutate=True)
        await bound_scope(account, payload.scope_id)
        async with app.state.sessions() as db:
            row = Conversation(id=uuid4().hex, account_id=account.id, scope_id=payload.scope_id)
            db.add(row)
            await db.commit()
            return conversation_public(row)

    @app.get("/api/conversations/{id}")
    async def get_conversation(id: str, request: Request) -> Any:
        return conversation_public(await owned(await current(request), id))

    @app.patch("/api/conversations/{id}")
    async def update_conversation(id: str, payload: ConversationPatch, request: Request) -> Any:
        account = await current(request, mutate=True)
        await owned(account, id)
        async with app.state.sessions() as db:
            row = await db.get(Conversation, id)
            if payload.title is not None:
                row.title = payload.title
            if payload.archived is not None:
                row.archived = payload.archived
            row.updated_at = time.time()
            await db.commit()
            return conversation_public(row)

    @app.get("/api/conversations/{id}/capabilities")
    async def capabilities(id: str, request: Request) -> Response:
        return await forward(
            "GET", "/api/agent/capabilities", query=await context(await current(request), id)
        )

    @app.get("/api/conversations/{id}/slash-candidates")
    async def candidates(id: str, request: Request) -> Any:
        ctx = await context(await current(request), id)
        try:
            results = await asyncio.gather(
                *(
                    app.state.http.get(f"/api/agent/{kind}", params=ctx)
                    for kind in ("skills", "scenes")
                )
            )
        except httpx.RequestError as exc:
            raise HTTPException(502, "Agent 服务暂时不可用") from exc
        items = []
        for result in results:
            if result.status_code != 200:
                return Response(
                    result.content, status_code=result.status_code, media_type="application/json"
                )
            items.extend(result.json()["items"])
        return {"items": items}

    @app.get("/api/conversations/{id}/messages")
    async def messages(
        id: str,
        request: Request,
        limit: int = Query(100, ge=1, le=200),
        before_sequence: int | None = Query(None, ge=1),
    ) -> Response:
        query = {**await context(await current(request), id), "limit": limit}
        if before_sequence is not None:
            query["before_sequence"] = before_sequence
        return await forward(
            "GET", f"/api/agent/conversations/{quote(id, safe='')}/messages", query=query
        )

    @app.get("/api/conversations/{id}/pending-ask")
    async def pending(id: str, request: Request) -> Response:
        return await forward(
            "GET",
            f"/api/agent/conversations/{quote(id, safe='')}/pending-ask",
            query=await context(await current(request), id),
        )

    @app.post("/api/conversations/{id}/chat/stream")
    async def chat(id: str, payload: Chat, request: Request) -> Response:
        account = await current(request, mutate=True)
        ctx = await context(account, id, write=True)
        result = await forward(
            "POST",
            "/api/agent/chat/stream",
            body={**ctx, **payload.model_dump(), "metadata": {}},
            stream=True,
        )
        if result.status_code == 200:
            async with app.state.sessions() as db:
                row = await db.get(Conversation, id)
                if row.title == "新对话" and payload.content:
                    row.title = payload.content.replace("\n", " ")[:80]
                row.updated_at = time.time()
                await db.commit()
        return result

    @app.post("/api/conversations/{id}/chat/ask-answer")
    async def ask(id: str, payload: Ask, request: Request) -> Response:
        return await forward(
            "POST",
            "/api/agent/chat/ask-answer",
            body={
                **await context(await current(request, mutate=True), id, write=True),
                **payload.model_dump(),
                "metadata": {},
            },
            stream=True,
        )

    @app.post("/api/conversations/{id}/chat/interrupt")
    async def interrupt(id: str, request: Request) -> Response:
        return await forward(
            "POST",
            f"/api/agent/conversations/{quote(id, safe='')}/interrupt",
            body=await context(await current(request, mutate=True), id),
        )

    @app.post("/api/conversations/{id}/attachments")
    async def upload(
        id: str,
        request: Request,
        request_id: Annotated[str, Form(min_length=1, max_length=64)],
        file: Annotated[UploadFile, File()],
    ) -> Response:
        ctx = await context(await current(request, mutate=True), id, write=True)
        data = await file.read(configuration.max_image_bytes + 1)
        await file.close()
        if len(data) > configuration.max_image_bytes:
            raise HTTPException(413, "图片超过上传限制")
        return await forward(
            "POST",
            "/api/agent/chat/attachments",
            data={**ctx, "request_id": request_id},
            files={"file": ("image", data, file.content_type or "application/octet-stream")},
        )

    @app.get("/api/conversations/{id}/attachments/{attachment_id}")
    async def download(id: str, attachment_id: str, request: Request) -> Response:
        return await forward(
            "GET",
            f"/api/agent/chat/attachments/{quote(attachment_id, safe='')}",
            query=await context(await current(request), id),
            stream=True,
        )

    return app
