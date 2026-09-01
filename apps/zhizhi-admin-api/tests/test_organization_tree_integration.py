"""Integration coverage for tenant-owned arbitrary-depth organization trees."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from gewu_core.config import BootstrapSettings
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiSettings
from zhizhi_platform.iam import JwtSettings, hash_password
from zhizhi_platform.iam.adapters.mysql.models import AdminUserModel

JWT_SIGNING_KEY = "zhizhi-organization-test-key-32-bytes"


def _authorized_client(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0)),
    )
    client = TestClient(create_admin_app(bootstrap=bootstrap, runtime=runtime))
    client.__enter__()
    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    with Session(engine) as session:
        session.add(
            AdminUserModel(
                id="root",
                username="root",
                normalized_username="ROOT",
                password_hash=hash_password("unused-test-password"),
                is_super=True,
            )
        )
        session.commit()
    engine.dispose()
    security = runtime._iam.identity_security if runtime._iam is not None else None
    assert security is not None
    token = security.issue_admin_token(user_id="root", username="root", is_super=True)
    return client, {
        "Cookie": f"zhizhi_admin_session={token}; zhizhi_admin_csrf=test",
        "X-CSRF-Token": "test",
    }


def _create_tenant(client: TestClient, headers: dict[str, str], code: str) -> str:
    response = client.post(
        "/api/admin/org/tenants",
        headers=headers,
        json={"tenant_code": code, "tenant_name": code.title()},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _create_unit(
    client: TestClient,
    headers: dict[str, str],
    tenant_id: str,
    *,
    key: str,
    parent_id: str | None = None,
    unit_type: str = "",
) -> dict[str, object]:
    response = client.post(
        f"/api/admin/org/tenants/{tenant_id}/organization-units",
        headers=headers,
        json={
            "parent_id": parent_id,
            "external_key": key,
            "name": key.title(),
            "unit_type": unit_type,
            "metadata": {"source": "test"},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_organization_tree_supports_arbitrary_depth_and_guards_its_shape(
    tmp_path: Path,
) -> None:
    client, headers = _authorized_client(tmp_path)
    try:
        tenant_id = _create_tenant(client, headers, "acme")
        other_tenant_id = _create_tenant(client, headers, "globex")
        root = _create_unit(client, headers, tenant_id, key="operations", unit_type="division")
        region = _create_unit(
            client,
            headers,
            tenant_id,
            key="north-region",
            parent_id=str(root["id"]),
            unit_type="region",
        )
        team = _create_unit(
            client,
            headers,
            tenant_id,
            key="delivery-team",
            parent_id=str(region["id"]),
            unit_type="team",
        )
        squad = _create_unit(
            client,
            headers,
            tenant_id,
            key="platform-squad",
            parent_id=str(team["id"]),
            unit_type="squad",
        )

        listing = client.get(
            f"/api/admin/org/tenants/{tenant_id}/organization-units",
            headers=headers,
        )
        assert listing.status_code == 200
        rows = listing.json()["organization_units"]
        assert {row["external_key"] for row in rows} == {
            "operations",
            "north-region",
            "delivery-team",
            "platform-squad",
        }
        by_key = {row["external_key"]: row for row in rows}
        assert by_key["north-region"]["parent_id"] == root["id"]
        assert by_key["delivery-team"]["parent_id"] == region["id"]
        assert by_key["platform-squad"]["parent_id"] == team["id"]
        assert by_key["platform-squad"]["metadata"] == {"source": "test"}

        cross_tenant = client.post(
            f"/api/admin/org/tenants/{other_tenant_id}/organization-units",
            headers=headers,
            json={"parent_id": root["id"], "external_key": "invalid"},
        )
        assert cross_tenant.status_code == 422

        cycle = client.patch(
            f"/api/admin/org/organization-units/{root['id']}",
            headers=headers,
            json={"parent_id": squad["id"]},
        )
        assert cycle.status_code == 422

        non_leaf_delete = client.delete(
            f"/api/admin/org/organization-units/{team['id']}", headers=headers
        )
        assert non_leaf_delete.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_fixed_level_organization_routes_are_absent() -> None:
    paths = create_admin_app().openapi()["paths"]
    assert "/api/admin/org/tenants/{tenant_id}/organization-units" in paths
    assert not any("/areas" in path for path in paths)
