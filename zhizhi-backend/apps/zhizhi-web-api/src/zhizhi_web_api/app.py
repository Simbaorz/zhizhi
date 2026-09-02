"""FastAPI transport for the embedded zhizhi Agent workbench."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, cast

from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict
from starlette.types import Scope

from gewu_agent_runtime.domain import StoredAttachment
from gewu_agent_runtime.persistence import IdempotencyConflictError
from gewu_agent_runtime.runtime import (
    AskExpiredError,
    AskNotPendingError,
    ConcurrentRunError,
    PrincipalMismatchError,
    SafeExecutionError,
)
from gewu_core.config import BootstrapSettings, load_bootstrap_settings_as
from gewu_core.errors import ApplicationError, ApplicationErrorKind
from gewu_core.http import (
    DownloadEgressMiddleware,
    HttpRequestBodyLimitMiddleware,
    UploadIngressMiddleware,
)
from gewu_core.http.downloads import BoundedMediaResponse
from gewu_core.http.request_limits import buffered_limited_upload_file
from zhizhi import (
    AgentContext,
    AgentTurnCommand,
    AgentUploadAttachmentCommand,
    AgentWorkbenchService,
    AskAnswerCommand,
    SlashCatalog,
)
from zhizhi_web_api.runtime import ZhizhiApiRuntime
from zhizhi_web_api.settings import WebApiBootstrapSettings
from zhizhi_web_api.sse import encode_sse_event, encode_stream_end, encode_stream_error


class InterruptResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    interrupted: bool


class ChatAttachmentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    attachment_id: str
    conversation_id: str
    original_name: str
    mime_type: str
    size_bytes: int


logger = logging.getLogger(__name__)


def create_app(
    *,
    service: AgentWorkbenchService | None = None,
    catalog: SlashCatalog | None = None,
    runtime: ZhizhiApiRuntime | None = None,
    bootstrap: BootstrapSettings | None = None,
) -> FastAPI:
    resolved_bootstrap = bootstrap or load_bootstrap_settings_as(WebApiBootstrapSettings)
    resolved_runtime = runtime
    if resolved_runtime is None and (service is None or catalog is None):
        resolved_runtime = ZhizhiApiRuntime(resolved_bootstrap)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if resolved_runtime is not None:
            await resolved_runtime.startup()
        try:
            yield
        finally:
            if resolved_runtime is not None:
                await resolved_runtime.shutdown()

    app_ = FastAPI(
        title="致知 Web API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app_.state.workbench_service = service
    app_.state.slash_catalog = catalog
    app_.state.runtime = resolved_runtime
    app_.add_middleware(
        HttpRequestBodyLimitMiddleware,
        body_limit_resolver=_agent_request_body_limit,
    )
    app_.add_middleware(
        UploadIngressMiddleware,
        request_selector=_is_attachment_upload,
    )
    app_.add_middleware(
        DownloadEgressMiddleware,
        request_selector=_is_attachment_download,
    )

    @app_.exception_handler(ApplicationError)
    async def application_error(_: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=_application_status(exc.kind),
            content={"code": exc.kind.value, "detail": exc.detail},
        )

    @app_.exception_handler(PrincipalMismatchError)
    async def owner_error(_: Request, __: PrincipalMismatchError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"code": "conversation_owner_mismatch", "detail": "Forbidden."},
        )

    @app_.exception_handler(ConcurrentRunError)
    async def concurrent_error(_: Request, __: ConcurrentRunError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"code": "conversation_busy", "detail": "A turn is already running."},
        )

    @app_.exception_handler(IdempotencyConflictError)
    async def idempotency_error(_: Request, __: IdempotencyConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"code": "idempotency_conflict", "detail": "request_id was reused."},
        )

    @app_.exception_handler(AskNotPendingError)
    @app_.exception_handler(AskExpiredError)
    async def ask_error(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"code": "ask_not_pending", "detail": "No resumable ask_user request."},
        )

    @app_.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app_.get("/readyz")
    async def ready() -> dict[str, str]:
        if resolved_runtime is not None and not resolved_runtime.ready:
            raise HTTPException(status_code=503, detail="process_not_ready")
        return {"status": "ready"}

    @app_.post("/api/agent/chat/stream")
    async def stream_chat(command: AgentTurnCommand) -> StreamingResponse:
        session = await _service(app_).start_turn(command)

        async def events() -> AsyncIterator[str]:
            try:
                async for event in session.stream():
                    yield encode_sse_event(
                        event,
                        run_id=session.run_id,
                        request_id=command.request_id,
                        conversation_id=session.conversation_id,
                    )
            except Exception as exc:  # noqa: BLE001
                yield _safe_stream_error(
                    exc,
                    run_id=session.run_id,
                    request_id=command.request_id,
                    conversation_id=session.conversation_id,
                )
            else:
                yield encode_stream_end(
                    run_id=session.run_id,
                    request_id=command.request_id,
                    conversation_id=session.conversation_id,
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app_.post("/api/agent/chat/ask-answer")
    async def answer_ask(command: AskAnswerCommand) -> StreamingResponse:
        session = await _service(app_).resume_ask(command)

        async def events() -> AsyncIterator[str]:
            try:
                async for event in session.stream():
                    yield encode_sse_event(
                        event,
                        run_id=session.run_id,
                        request_id=command.request_id,
                        conversation_id=session.conversation_id,
                    )
            except Exception as exc:  # noqa: BLE001
                yield _safe_stream_error(
                    exc,
                    run_id=session.run_id,
                    request_id=command.request_id,
                    conversation_id=session.conversation_id,
                )
            else:
                yield encode_stream_end(
                    run_id=session.run_id,
                    request_id=command.request_id,
                    conversation_id=session.conversation_id,
                )

        return StreamingResponse(events(), media_type="text/event-stream")

    @app_.get("/api/agent/capabilities")
    async def capabilities(
        context: Annotated[AgentContext, Depends(agent_context)],
    ) -> object:
        return await _service(app_).capabilities(context)

    @app_.post(
        "/api/agent/chat/attachments",
        response_model=ChatAttachmentResponse,
    )
    async def upload_attachment(
        request: Request,
        conversation_id: Annotated[str, Form(min_length=1, max_length=255)],
        tenant_id: Annotated[str, Form(min_length=1, max_length=64)],
        active_organization_unit_id: Annotated[str, Form(max_length=64)],
        principal_id: Annotated[str, Form(min_length=1, max_length=128)],
        principal_type: Annotated[str, Form(min_length=1, max_length=32)],
        request_id: Annotated[str, Form(min_length=1, max_length=64)],
        file: Annotated[UploadFile, File()],
    ) -> ChatAttachmentResponse:
        service_ = _service(app_)
        async with buffered_limited_upload_file(
            request,
            file,
            service_.max_image_bytes,
        ) as data:
            attachment = await service_.upload_attachment(
                AgentUploadAttachmentCommand(
                    conversation_id=conversation_id,
                    tenant_id=tenant_id,
                    active_organization_unit_id=active_organization_unit_id,
                    principal_id=principal_id,
                    principal_type=principal_type,
                    request_id=request_id,
                    data=data,
                )
            )
        return _attachment_response(attachment)

    @app_.get(
        "/api/agent/chat/attachments/{attachment_id}",
        response_class=Response,
        responses={
            200: {
                "content": {
                    "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                    "image/png": {"schema": {"type": "string", "format": "binary"}},
                }
            }
        },
    )
    async def download_attachment(
        attachment_id: Annotated[str, Path(min_length=1, max_length=64)],
        conversation_id: Annotated[str, Query(min_length=1, max_length=255)],
        context: Annotated[AgentContext, Depends(agent_context)],
    ) -> Response:
        service_ = _service(app_)
        attachment = await service_.resolve_attachment(
            _path_context(context, conversation_id),
            attachment_id,
        )
        return BoundedMediaResponse(
            loader=lambda: service_.read_attachment_data(attachment),
            reservation_size_bytes=service_.max_image_bytes,
            media_type=attachment.mime_type,
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app_.get("/api/agent/skills")
    async def skills(context: Annotated[AgentContext, Depends(agent_context)]) -> object:
        return {"items": await _catalog(app_).list_skills(context)}

    @app_.get("/api/agent/scenes")
    async def scenes(context: Annotated[AgentContext, Depends(agent_context)]) -> object:
        return {"items": await _catalog(app_).list_scenes(context)}

    @app_.get("/api/agent/conversations/{conversation_id}/messages")
    async def messages(
        conversation_id: Annotated[str, Path(min_length=1, max_length=255)],
        context: Annotated[AgentContext, Depends(agent_context)],
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        before_sequence: Annotated[int | None, Query(ge=1)] = None,
    ) -> object:
        return await _service(app_).list_messages(
            _path_context(context, conversation_id),
            limit=limit,
            before_sequence=before_sequence,
        )

    @app_.get("/api/agent/conversations/{conversation_id}/pending-ask")
    async def pending_ask(
        conversation_id: Annotated[str, Path(min_length=1, max_length=255)],
        context: Annotated[AgentContext, Depends(agent_context)],
    ) -> object:
        return await _service(app_).state(_path_context(context, conversation_id))

    @app_.post("/api/agent/conversations/{conversation_id}/interrupt")
    async def interrupt(
        conversation_id: Annotated[str, Path(min_length=1, max_length=255)],
        context: Annotated[AgentContext, Body()],
    ) -> InterruptResult:
        interrupted = await _service(app_).interrupt(_path_context(context, conversation_id))
        return InterruptResult(interrupted=interrupted)

    return app_


def _service(app_: FastAPI) -> AgentWorkbenchService:
    service = app_.state.workbench_service
    if service is None and app_.state.runtime is not None:
        service = app_.state.runtime.service
    if service is None:
        raise HTTPException(status_code=503, detail="workbench_service_not_ready")
    return cast(AgentWorkbenchService, service)


def _catalog(app_: FastAPI) -> SlashCatalog:
    catalog = app_.state.slash_catalog
    if catalog is None and app_.state.runtime is not None:
        catalog = app_.state.runtime.catalog
    if catalog is None:
        raise HTTPException(status_code=503, detail="slash_catalog_not_ready")
    return cast(SlashCatalog, catalog)


def agent_context(
    request: Request,
    tenant_id: Annotated[str, Query(min_length=1, max_length=64)],
    active_organization_unit_id: Annotated[str, Query(max_length=64)],
    principal_id: Annotated[str, Query(min_length=1, max_length=128)],
    principal_type: Annotated[str, Query(min_length=1, max_length=32)],
) -> AgentContext:
    return AgentContext(
        conversation_id=request.path_params.get("conversation_id", "catalog"),
        tenant_id=tenant_id,
        active_organization_unit_id=active_organization_unit_id,
        principal_id=principal_id,
        principal_type=principal_type,
    )


def _path_context(context: AgentContext, conversation_id: str) -> AgentContext:
    return context.model_copy(update={"conversation_id": conversation_id})


def _attachment_response(attachment: StoredAttachment) -> ChatAttachmentResponse:
    return ChatAttachmentResponse(
        attachment_id=attachment.attachment_id,
        conversation_id=attachment.conversation_id,
        original_name=attachment.original_name,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
    )


def _agent_request_body_limit(scope: Scope) -> int | None:
    path = str(scope.get("path") or "").rstrip("/")
    if path == "/api/agent/chat/attachments":
        return _media_max_image_bytes(scope) + 64 * 1024
    if path.startswith("/api/agent/"):
        return 256 * 1024
    return None


def _is_attachment_upload(scope: Scope) -> bool:
    return (
        scope["type"] == "http"
        and str(scope.get("method") or "").upper() == "POST"
        and str(scope.get("path") or "").rstrip("/") == "/api/agent/chat/attachments"
    )


def _is_attachment_download(scope: Scope) -> bool:
    return (
        scope["type"] == "http"
        and str(scope.get("method") or "").upper() in {"GET", "HEAD"}
        and str(scope.get("path") or "").startswith("/api/agent/chat/attachments/")
    )


def _media_max_image_bytes(scope: Scope) -> int:
    state = getattr(scope.get("app"), "state", None)
    service = getattr(state, "workbench_service", None)
    if service is not None:
        value = getattr(service, "max_image_bytes", None)
        if isinstance(value, int):
            return value
    runtime = getattr(state, "runtime", None)
    media = getattr(getattr(runtime, "settings", None), "media", None)
    value = getattr(media, "max_image_bytes", None)
    return value if isinstance(value, int) else 5 * 1024 * 1024


app = create_app()


def _application_status(kind: ApplicationErrorKind) -> int:
    return {
        ApplicationErrorKind.UNAUTHENTICATED: 401,
        ApplicationErrorKind.FORBIDDEN: 403,
        ApplicationErrorKind.NOT_FOUND: 404,
        ApplicationErrorKind.CONFLICT: 409,
        ApplicationErrorKind.PAYLOAD_TOO_LARGE: 413,
        ApplicationErrorKind.UNAVAILABLE: 503,
        ApplicationErrorKind.TIMEOUT: 504,
    }.get(kind, 422)


def _safe_stream_error(
    exc: Exception,
    *,
    run_id: str,
    request_id: str,
    conversation_id: str,
) -> str:
    if isinstance(exc, SafeExecutionError):
        code, message = exc.code, exc.message
    else:
        code, message = "agent_unavailable", "Agent execution is temporarily unavailable."
    logger.error(
        "Agent stream failed exception_type=%s run_id=%s request_id=%s conversation_id=%s",
        type(exc).__name__,
        run_id,
        request_id,
        conversation_id,
    )
    return encode_stream_error(
        code=code,
        message=message,
        run_id=run_id,
        request_id=request_id,
        conversation_id=conversation_id,
    )
