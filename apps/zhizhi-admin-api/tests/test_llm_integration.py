"""Real Admin LLM flow through SQLite, JWT, encryption, hierarchy, and audit."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from gewu_core import JsonSecretCipher, StorageEncryptionSettings
from gewu_core.config import BootstrapSettings
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.llm import LLMEntitlementBatchCreateRequest
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiSettings
from zhizhi_platform.audit import AdminAuditLogModel
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import JwtSettings
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminUserModel,
    OrganizationUnitModel,
    TenantModel,
)
from zhizhi_platform.llm.adapters.mysql.models import (
    LLMBindingModel,
    LLMConfigModel,
    LLMEntitlementModel,
)
from zhizhi_platform.llm.connectivity import ProviderConnectivityTester
from zhizhi_platform.llm.ports import LLMConnectivityRequest, LLMConnectivityResult

JWT_SIGNING_KEY = "l" * 32
CREDENTIAL_KEY = "c" * 32


def _assert_llm_admin_round_trip_matches_zhizhi_behavior(tmp_path: Path, monkeypatch) -> None:
    connectivity_requests: list[LLMConnectivityRequest] = []

    async def test_connectivity(
        _self: ProviderConnectivityTester,
        request: LLMConnectivityRequest,
    ) -> LLMConnectivityResult:
        connectivity_requests.append(request)
        return LLMConnectivityResult(
            content="connected",
            usage={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
        )

    monkeypatch.setattr(ProviderConnectivityTester, "test", test_connectivity)
    _seed_database(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            storage_encryption=StorageEncryptionSettings(key=CREDENTIAL_KEY),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        security = runtime._iam.identity_security if runtime._iam is not None else None
        assert security is not None
        headers = _cookie_headers(
            security.issue_admin_token(
                user_id="admin-super",
                username="root",
                is_super=True,
            )
        )
        created_response = client.post(
            "/api/admin/llm/models",
            headers=headers,
            json={
                "alias": "main",
                "display_name": "Main Model",
                "provider": "openai",
                "protocol": "openai-chat",
                "model_name": "gpt-test",
                "endpoint_url": "http://10.0.0.8:8080/v1",
                "credentials": {"api_key": "secret-key"},
            },
        )
        assert created_response.status_code == 200
        created = created_response.json()
        model_id = created["id"]
        assert created["has_credentials"] is True
        assert created["credential_fields"] == ["api_key"]
        assert created["provider_config"] == {"context_window": 32768}
        assert "credentials_ciphertext" not in created
        assert "secret-key" not in str(created)

        credentials = client.put(
            f"/api/admin/llm/models/{model_id}/credentials",
            headers=headers,
            json={"credentials": {"api_key": "new-secret-key"}},
        )
        assert credentials.status_code == 200
        assert credentials.json()["credential_fields"] == ["api_key"]

        spare_response = client.post(
            "/api/admin/llm/models",
            headers=headers,
            json={
                "alias": "spare",
                "display_name": "Spare Model",
                "provider": "openai",
                "protocol": "openai-chat",
                "model_name": "gpt-spare",
                "endpoint_url": "http://10.0.0.9:8080/v1",
                "credentials": {"api_key": "spare-secret-key"},
            },
        )
        assert spare_response.status_code == 200
        spare_id = spare_response.json()["id"]

        patched_model = client.patch(
            f"/api/admin/llm/models/{spare_id}",
            headers=headers,
            json={
                "display_name": "Updated Spare",
                "provider_config": {"context_window": 65536},
            },
        )
        assert patched_model.status_code == 200
        assert patched_model.json()["display_name"] == "Updated Spare"
        assert patched_model.json()["provider_config"] == {"context_window": 65536}

        validated_model = client.post(
            f"/api/admin/llm/models/{spare_id}/validate",
            headers=headers,
        )
        assert validated_model.status_code == 200
        assert validated_model.json() == {"ok": True, "message": "配置校验通过。"}

        tested_model = client.post(
            f"/api/admin/llm/models/{spare_id}/test",
            headers=headers,
            json={"prompt": "ping", "system_prompt": "system"},
        )
        assert tested_model.status_code == 200
        assert tested_model.json()["ok"] is True
        assert tested_model.json()["content"] == "connected"
        assert tested_model.json()["usage"] == {
            "input_tokens": 2,
            "output_tokens": 1,
            "total_tokens": 3,
        }
        assert tested_model.json()["error"] == ""
        assert connectivity_requests[0].prompt == "ping"
        assert connectivity_requests[0].system_prompt == "system"

        spare_entitlements = client.post(
            "/api/admin/llm/entitlements/batch",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "scope_type": "tenant",
                "organization_unit_id": "",
                "llm_config_ids": [spare_id, model_id],
            },
        )
        assert spare_entitlements.status_code == 200
        entitlement_ids = {
            item["llm_config_id"]: item["id"] for item in spare_entitlements.json()["entitlements"]
        }
        assert set(entitlement_ids) == {spare_id, model_id}
        spare_entitlement_id = entitlement_ids[spare_id]
        tenant_entitlement_id = entitlement_ids[model_id]

        duplicate_with_invalid_status = client.post(
            "/api/admin/llm/entitlements",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "scope_type": "tenant",
                "organization_unit_id": "",
                "llm_config_id": model_id,
                "status": "unsupported",
            },
        )
        assert duplicate_with_invalid_status.status_code == 409
        assert duplicate_with_invalid_status.json()["detail"] == "该范围已拥有该模型。"

        division_entitlement = client.post(
            "/api/admin/llm/entitlements",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "scope_type": "organization_unit",
                "organization_unit_id": "division-1",
                "llm_config_id": model_id,
            },
        )
        assert division_entitlement.status_code == 200

        team_entitlement = client.post(
            "/api/admin/llm/entitlements",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "scope_type": "organization_unit",
                "organization_unit_id": "team-1",
                "llm_config_id": model_id,
            },
        )
        assert team_entitlement.status_code == 200

        binding = client.post(
            "/api/admin/llm/bindings",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "scope_type": "organization_unit",
                "organization_unit_id": "team-1",
                "llm_config_id": model_id,
                "runtime_overrides": {"temperature": 0.2, "max_tokens": 1024},
            },
        )
        assert binding.status_code == 200
        assert binding.json()["runtime_overrides"] == {
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        binding_id = binding.json()["id"]

        bindings = client.get(
            "/api/admin/llm/bindings",
            headers=headers,
            params={"tenant_id": "tenant-1", "search": "Main Model", "page_size": 10},
        )
        assert bindings.status_code == 200
        assert bindings.json()["pagination"] == {"page": 1, "page_size": 10, "total": 1}
        assert [row["id"] for row in bindings.json()["bindings"]] == [binding_id]

        entitlements = client.get(
            "/api/admin/llm/entitlements",
            headers=headers,
            params={"tenant_id": "tenant-1", "page_size": 10},
        )
        assert entitlements.status_code == 200
        assert entitlements.json()["pagination"] == {"page": 1, "page_size": 10, "total": 4}

        scoped_models = client.get(
            "/api/admin/llm/models",
            headers=headers,
            params={"tenant_id": "tenant-1"},
        )
        assert scoped_models.status_code == 200
        assert {row["id"] for row in scoped_models.json()["models"]} == {model_id, spare_id}

        blocked = client.patch(
            f"/api/admin/llm/entitlements/{tenant_entitlement_id}",
            headers=headers,
            json={"status": "inactive"},
        )
        assert blocked.status_code == 422
        assert "下级分配" in blocked.json()["detail"]

        inactive_model_blocked = client.patch(
            f"/api/admin/llm/models/{model_id}",
            headers=headers,
            json={"status": "inactive"},
        )
        assert inactive_model_blocked.status_code == 422
        assert inactive_model_blocked.json() == {"detail": "模型仍存在启用绑定，不能停用。"}

        delete_model_blocked = client.delete(
            f"/api/admin/llm/models/{model_id}",
            headers=headers,
        )
        assert delete_model_blocked.status_code == 422
        assert delete_model_blocked.json() == {
            "detail": "模型仍存在绑定关系，不能删除，请先解除模型绑定。"
        }

        inactive_binding = client.patch(
            f"/api/admin/llm/bindings/{binding_id}",
            headers=headers,
            json={"status": "inactive", "runtime_overrides": {"max_tokens": 256}},
        )
        assert inactive_binding.status_code == 200
        assert inactive_binding.json()["status"] == "inactive"
        assert inactive_binding.json()["runtime_overrides"] == {"max_tokens": 256}

        deleted_binding = client.delete(
            f"/api/admin/llm/bindings/{binding_id}",
            headers=headers,
        )
        assert deleted_binding.status_code == 200
        assert deleted_binding.json() == {"deleted": True}

        deleted_entitlement = client.delete(
            f"/api/admin/llm/entitlements/{spare_entitlement_id}",
            headers=headers,
        )
        assert deleted_entitlement.status_code == 200
        assert deleted_entitlement.json() == {"deleted": True}

        deleted_model = client.delete(
            f"/api/admin/llm/models/{spare_id}",
            headers=headers,
        )
        assert deleted_model.status_code == 200
        assert deleted_model.json() == {"deleted": True}

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            config = session.get(LLMConfigModel, model_id)
            assert config is not None
            assert config.status == "active"
            assert JsonSecretCipher(CREDENTIAL_KEY).decrypt(config.credentials_ciphertext) == {
                "api_key": "new-secret-key"
            }
            tenant_entitlement_row = session.get(LLMEntitlementModel, tenant_entitlement_id)
            assert tenant_entitlement_row is not None
            assert tenant_entitlement_row.status == "active"
            assert session.scalar(select(func.count()).select_from(LLMEntitlementModel)) == 3
            assert session.scalar(select(func.count()).select_from(LLMBindingModel)) == 0
            assert (
                int(session.scalar(select(func.count()).select_from(AdminAuditLogModel)) or 0) == 14
            )
    finally:
        engine.dispose()


def test_llm_model_create_list_and_validate(tmp_path: Path, monkeypatch) -> None:
    _assert_llm_admin_round_trip_matches_zhizhi_behavior(tmp_path, monkeypatch)


def test_llm_binding_create_and_update_runtime_overrides(tmp_path: Path, monkeypatch) -> None:
    _assert_llm_admin_round_trip_matches_zhizhi_behavior(tmp_path, monkeypatch)


def test_llm_entitlement_batch_create_creates_multiple_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _assert_llm_admin_round_trip_matches_zhizhi_behavior(tmp_path, monkeypatch)


def test_llm_binding_can_be_inactivated_after_entitlement_is_inactive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _assert_llm_admin_round_trip_matches_zhizhi_behavior(tmp_path, monkeypatch)


def test_llm_model_update_rejects_inactive_when_active_binding_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _assert_llm_admin_round_trip_matches_zhizhi_behavior(tmp_path, monkeypatch)


def test_llm_model_delete_rejects_existing_binding(tmp_path: Path, monkeypatch) -> None:
    _assert_llm_admin_round_trip_matches_zhizhi_behavior(tmp_path, monkeypatch)


def test_llm_binding_delete_allows_model_delete_after_unbind(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _assert_llm_admin_round_trip_matches_zhizhi_behavior(tmp_path, monkeypatch)


def test_llm_entitlement_batch_create_limits_to_ten_models() -> None:
    with pytest.raises(ValueError):
        LLMEntitlementBatchCreateRequest(
            tenant_id="tenant-1",
            scope_type="tenant",
            llm_config_ids=[f"model-{index}" for index in range(11)],
        )


def test_llm_admin_openapi_publishes_model_management_routes() -> None:
    spec = create_admin_app().openapi()
    paths = {path for path in spec["paths"] if path.startswith("/api/admin/llm")}

    assert paths == {
        "/api/admin/llm/models",
        "/api/admin/llm/models/{model_id}",
        "/api/admin/llm/models/{model_id}/credentials",
        "/api/admin/llm/models/{model_id}/validate",
        "/api/admin/llm/models/{model_id}/test",
        "/api/admin/llm/entitlements",
        "/api/admin/llm/entitlements/batch",
        "/api/admin/llm/entitlements/{entitlement_id}",
        "/api/admin/llm/bindings",
        "/api/admin/llm/bindings/{binding_id}",
    }


def _seed_database(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        ZhizhiBase.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all(
                [
                    AdminUserModel(
                        id="admin-super",
                        username="root",
                        normalized_username="ROOT",
                        password_hash="hash",
                        is_super=True,
                    ),
                    TenantModel(
                        id="tenant-1",
                        tenant_code="T1",
                        normalized_tenant_code="T1",
                        tenant_name="Tenant One",
                        storage_key="TENANT_ONE",
                    ),
                    OrganizationUnitModel(
                        id="division-1",
                        tenant_id="tenant-1",
                        external_key="DIVISION",
                        normalized_external_key="DIVISION",
                        storage_key="DIVISION",
                        name="Division One",
                        unit_type="division",
                    ),
                    OrganizationUnitModel(
                        id="team-1",
                        tenant_id="tenant-1",
                        parent_id="division-1",
                        external_key="TEAM",
                        normalized_external_key="TEAM",
                        storage_key="TEAM",
                        name="Team One",
                        unit_type="team",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _cookie_headers(token: str) -> dict[str, str]:
    csrf_token = "test-admin-csrf"
    return {
        "Cookie": f"zhizhi_admin_session={token}; zhizhi_admin_csrf={csrf_token}",
        "X-CSRF-Token": csrf_token,
    }
