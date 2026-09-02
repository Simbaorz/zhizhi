"""Automatic Admin HTTP mutation audit coverage."""

import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from zhizhi_admin_api.mutation_audit import (
    AdminMutationAuditMiddleware,
    attach_admin_audit_context,
)
from zhizhi_platform.audit import AdminAuditActor, AdminAuditLog, AdminAuditWriter


class AuditRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.logs: list[AdminAuditLog] = []

    async def append(self, log: AdminAuditLog) -> AdminAuditLog:
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.logs.append(log)
        return log


def test_mutation_audit_records_fields_without_sensitive_values() -> None:
    repository = AuditRepository()
    client = TestClient(_app(repository))

    response = client.post(
        "/api/admin/resources/resource-1",
        headers={"x-request-id": "request-1"},
        json={
            "tenant_id": "tenant-1",
            "display_name": "Visible",
            "encrypted_password": "must-not-be-logged",
        },
    )
    read_response = client.get("/api/admin/resources")

    assert response.status_code == 200
    assert read_response.status_code == 200
    assert len(repository.logs) == 1
    log = repository.logs[0]
    assert log.target_resource_id == "resource-1"
    assert log.target_tenant_id == "tenant-1"
    assert log.scope_summary["correlation_id"] == "request-1"
    assert log.scope_summary["sensitive_fields_changed"] == ["encrypted_password"]
    assert "must-not-be-logged" not in str(log.model_dump(mode="json"))


def test_mutation_audit_failure_does_not_change_successful_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger="zhizhi_platform.audit.writer"):
        response = TestClient(_app(AuditRepository(fail=True))).post(
            "/api/admin/resources/resource-1",
            json={"tenant_id": "tenant-1", "password": "audit-body-private-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"id": "resource-1"}
    assert "exception_type=RuntimeError" in caplog.text
    assert "audit unavailable" not in caplog.text
    assert "audit-body-private-secret" not in caplog.text


def test_middleware_absorbs_unexpected_writer_failure_without_logging_exception_body(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_write(_writer: AdminAuditWriter, **_values: object) -> None:
        raise RuntimeError("middleware-audit-private-secret")

    monkeypatch.setattr(AdminAuditWriter, "write", fail_write)
    with caplog.at_level(logging.ERROR, logger="zhizhi_admin_api.mutation_audit"):
        response = TestClient(_app(AuditRepository())).post(
            "/api/admin/resources/resource-1",
            json={"tenant_id": "tenant-1", "password": "audit-body-private-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"id": "resource-1"}
    assert "Failed to append automatic Admin mutation audit" in caplog.text
    assert "method=POST" in caplog.text
    assert "route=/api/admin/resources/{resource_id}" in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert "middleware-audit-private-secret" not in caplog.text
    assert "audit-body-private-secret" not in caplog.text


def _app(repository: AuditRepository) -> FastAPI:
    app = FastAPI()
    app.add_middleware(AdminMutationAuditMiddleware)

    @app.post("/api/admin/resources/{resource_id}")
    async def mutate(resource_id: str, request: Request) -> dict[str, object]:
        attach_admin_audit_context(
            request,
            actor=AdminAuditActor(admin_user_id="admin-1", is_super=True),
            writer=AdminAuditWriter(repository),
        )
        return {"id": resource_id}

    @app.get("/api/admin/resources")
    async def read(request: Request) -> dict[str, object]:
        attach_admin_audit_context(
            request,
            actor=AdminAuditActor(admin_user_id="admin-1", is_super=True),
            writer=AdminAuditWriter(repository),
        )
        return {"items": []}

    return app
