"""Real Admin authentication flow through RSA, SQLite, RBAC, and JWT."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from gewu_core import ApplicationError, ApplicationErrorKind
from gewu_core.config import BootstrapSettings
from gewu_core.http import PasswordTransportSettings, RsaPasswordTransport
from gewu_core.redis import RedisConnectionSettings, RedisMode
from zhizhi_admin_api import runtime as runtime_module
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.dependencies import get_admin_auth_service
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiSettings
from zhizhi_platform import ZhizhiRedisSettings
from zhizhi_platform.audit import AdminAuditLogModel
from zhizhi_platform.database import ZhizhiBase
from zhizhi_platform.iam import JwtSettings, LoginThrottleSettings, hash_password
from zhizhi_platform.iam.adapters.mysql.models import (
    AdminPermissionModel,
    AdminRoleModel,
    AdminRolePermissionModel,
    AdminTenantMemberModel,
    AdminTenantRoleModel,
    AdminTenantScopeModel,
    AdminUserModel,
)

JWT_SIGNING_KEY = "admin-auth-integration-signing-key"


@pytest.mark.parametrize(
    ("kind", "detail", "expected_status"),
    [
        (ApplicationErrorKind.UNAUTHENTICATED, "Admin token has been revoked.", 401),
        (
            ApplicationErrorKind.UNAVAILABLE,
            "Admin session tenant memberships exceed the server limit.",
            503,
        ),
    ],
)
def test_admin_session_application_errors_preserve_zhizhi_http_mapping(
    tmp_path: Path,
    kind: ApplicationErrorKind,
    detail: str,
    expected_status: int,
) -> None:
    app = _app_with_default_settings(tmp_path)
    app.dependency_overrides[get_admin_auth_service] = lambda: _FailingSessionService(
        kind=kind,
        detail=detail,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/admin/auth/me",
            headers={"Cookie": "zhizhi_admin_session=syntactically-valid-test-token"},
        )

    assert response.status_code == expected_status
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize("token_version", [True, "0", 0.0, None])
def test_admin_session_rejects_non_integer_token_versions_before_loading_session(
    tmp_path: Path,
    token_version: object,
) -> None:
    service = _InvalidVersionSessionService(token_version)
    app = _app_with_default_settings(tmp_path)
    app.dependency_overrides[get_admin_auth_service] = lambda: service

    with TestClient(app) as client:
        response = client.get(
            "/api/admin/auth/me",
            headers={"Cookie": "zhizhi_admin_session=syntactically-valid-test-token"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Admin session is missing, expired, or revoked."}
    assert not service.session_loaded


def test_admin_authentication_round_trip_matches_zhizhi_behavior(
    tmp_path: Path,
) -> None:
    key_path = _write_private_key(tmp_path)
    _seed_admin_database(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            password_transport=PasswordTransportSettings(private_key_path=str(key_path)),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)

        plaintext_login = client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "password": "secret"},
        )
        assert plaintext_login.status_code == 422

        invalid_envelope = client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "encrypted_password": "plaintext"},
        )
        assert invalid_envelope.status_code == 400
        assert invalid_envelope.json() == {"detail": "Invalid encrypted password."}

        login = client.post(
            "/api/admin/auth/login",
            json={
                "username": "admin",
                "encrypted_password": transport.encrypt_for_transport("secret"),
            },
        )
        assert login.status_code == 200
        login_payload = login.json()
        assert "token" not in login_payload
        session_token = client.cookies.get("zhizhi_admin_session")
        csrf_token = client.cookies.get("zhizhi_admin_csrf")
        assert session_token
        assert csrf_token
        assert login_payload["user"]["username"] == "admin"
        assert [item["permission_code"] for item in login_payload["permissions"]] == ["org.view"]
        assert [item["path"] for item in login_payload["navigation"]] == ["/org"]

        csrf_headers = {"X-CSRF-Token": csrf_token}
        me = client.get("/api/admin/auth/me")
        assert me.status_code == 200
        assert me.json()["is_super"] is False
        assert me.json()["navigation"] == login_payload["navigation"]

        navigation = client.get("/api/admin/auth/navigation")
        assert navigation.status_code == 200
        assert navigation.json() == {"items": me.json()["navigation"]}

        plaintext_change = client.post(
            "/api/admin/auth/me/password",
            headers=csrf_headers,
            json={
                "current_password": "secret",
                "new_password": "new-secret",
            },
        )
        assert plaintext_change.status_code == 422

        profile = client.patch(
            "/api/admin/auth/me/profile",
            headers=csrf_headers,
            json={
                "display_name": " Admin One ",
                "phone": " 13900000000 ",
                "email": " ADMIN@EXAMPLE.COM ",
            },
        )
        assert profile.status_code == 200
        assert profile.json()["user"]["display_name"] == "Admin One"
        assert profile.json()["user"]["phone"] == "13900000000"
        assert profile.json()["user"]["email"] == "admin@example.com"

        changed = client.post(
            "/api/admin/auth/me/password",
            headers=csrf_headers,
            json={
                "encrypted_current_password": transport.encrypt_for_transport("secret"),
                "encrypted_new_password": transport.encrypt_for_transport("new-secret"),
            },
        )
        assert changed.status_code == 200
        assert changed.json() == {"ok": True}
        assert client.cookies.get("zhizhi_admin_session") is None
        assert client.cookies.get("zhizhi_admin_csrf") is None
        client.cookies.set("zhizhi_admin_session", session_token, path="/api/admin")
        revoked = client.get("/api/admin/auth/me")
        assert revoked.status_code == 401
        assert revoked.json() == {"detail": "Admin token has been revoked."}
        client.cookies.clear()

        old_password = client.post(
            "/api/admin/auth/login",
            json={
                "username": "admin",
                "encrypted_password": transport.encrypt_for_transport("secret"),
            },
        )
        assert old_password.status_code == 401
        assert old_password.json() == {"detail": "用户名或密码错误。"}

        new_login = client.post(
            "/api/admin/auth/login",
            json={
                "username": "admin",
                "encrypted_password": transport.encrypt_for_transport("new-secret"),
            },
        )
        assert new_login.status_code == 200
        assert "token" not in new_login.json()
        new_session_token = client.cookies.get("zhizhi_admin_session")
        new_csrf_token = client.cookies.get("zhizhi_admin_csrf")
        assert new_session_token
        assert new_csrf_token
        logout = client.post(
            "/api/admin/auth/logout",
            headers={"X-CSRF-Token": new_csrf_token},
        )
        assert logout.status_code == 200
        assert logout.json() == {"ok": True}
        assert client.cookies.get("zhizhi_admin_session") is None
        assert client.cookies.get("zhizhi_admin_csrf") is None
        client.cookies.set("zhizhi_admin_session", new_session_token, path="/api/admin")
        assert client.get("/api/admin/auth/me").status_code == 401

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            audit_rows = list(session.scalars(select(AdminAuditLogModel)))
    finally:
        engine.dispose()
    assert [row.action for row in audit_rows].count("admin.http.patch") == 1
    assert [row.action for row in audit_rows].count("admin.http.post") == 2
    password_audit = next(
        row for row in audit_rows if "sensitive_fields_changed" in row.scope_summary
    )
    assert password_audit.scope_summary["sensitive_fields_changed"] == [
        "encrypted_current_password",
        "encrypted_new_password",
    ]
    assert "new-secret" not in str(password_audit.scope_summary)


def test_admin_navigation_uses_exact_current_permission_codes(tmp_path: Path) -> None:
    _seed_admin_database(tmp_path)
    _add_admin_permissions(
        tmp_path,
        "admins.view",
        "scene_git.view",
        "dashboard.view",
        "admin_content.view",
    )
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0)),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        headers = _admin_headers(runtime)
        response = client.get("/api/admin/auth/navigation", headers=headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["path"] for item in items] == ["/org", "/accounts", "/scene-git"]
    account_item = next(item for item in items if item["path"] == "/accounts")
    assert account_item["permission_code"] == ""
    assert account_item["permission_codes"] == ["admins.view"]
    assert all(item["path"] not in {"/global", "/content"} for item in items)


def test_admin_auth_me_returns_navigation(tmp_path: Path) -> None:
    _seed_admin_database(tmp_path)
    _promote_admin_to_super(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0)),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        security = runtime._iam.identity_security if runtime._iam is not None else None
        assert security is not None
        token = security.issue_admin_token(
            user_id="admin-1",
            username="admin",
            is_super=True,
        )
        response = client.get(
            "/api/admin/auth/me",
            headers={"Cookie": f"zhizhi_admin_session={token}"},
        )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "admin"
    paths = [item["path"] for item in response.json()["navigation"]]
    assert "/dashboard" not in paths
    assert "/global" in paths
    assert "/scenes" in paths
    assert paths[0] == "/global"


def test_admin_profile_conflict_priority_and_rollback_match_zhizhi(
    tmp_path: Path,
) -> None:
    _seed_admin_database(tmp_path)
    _seed_conflicting_admin(tmp_path)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0)),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        headers = _admin_headers(runtime)
        phone_first = client.patch(
            "/api/admin/auth/me/profile",
            headers=headers,
            json={
                "display_name": "Changed",
                "phone": "13900000000",
                "email": "TAKEN@EXAMPLE.COM",
            },
        )
        email_second = client.patch(
            "/api/admin/auth/me/profile",
            headers=headers,
            json={"display_name": "Changed", "email": "TAKEN@EXAMPLE.COM"},
        )

    assert phone_first.status_code == 409
    assert phone_first.json() == {"detail": "手机号已被其他管理员账号使用。"}
    assert email_second.status_code == 409
    assert email_second.json() == {"detail": "邮箱已被其他管理员账号使用。"}

    engine = create_engine(f"sqlite:///{tmp_path / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            user = session.get(AdminUserModel, "admin-1")
            audit_rows = list(session.scalars(select(AdminAuditLogModel)))
            assert user is not None
            assert user.display_name == "Admin"
            assert user.phone is None
            assert user.email is None
            assert all(row.action != "admin.http.patch" for row in audit_rows)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [("credential", 401), ("envelope", 400)],
)
def test_admin_runtime_counts_credential_and_envelope_failures_in_redis_throttle(
    monkeypatch,
    tmp_path: Path,
    failure: str,
    expected_status: int,
) -> None:
    key_path = _write_private_key(tmp_path)
    _seed_admin_database(tmp_path)
    redis = FakeRedisClient()
    monkeypatch.setattr(runtime_module, "RedisClient", lambda settings: redis)
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_SIGNING_KEY, leeway_seconds=0),
            password_transport=PasswordTransportSettings(private_key_path=str(key_path)),
            login_throttle=LoginThrottleSettings(
                max_failures=1,
                window_seconds=30,
                lockout_seconds=30,
            ),
            redis=_redis_settings(),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        payload = {
            "username": "admin",
            "encrypted_password": (
                transport.encrypt_for_transport("bad") if failure == "credential" else "plaintext"
            ),
        }
        first = client.post("/api/admin/auth/login", json=payload)
        second = client.post(
            "/api/admin/auth/login",
            json={
                "username": "admin",
                "encrypted_password": transport.encrypt_for_transport("secret"),
            },
        )

        assert first.status_code == expected_status
        assert second.status_code == 429
        assert second.headers["retry-after"] == "30"
        assert redis.initialized
        assert len(redis.values) == 2

    assert redis.closed


def _seed_admin_database(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    ZhizhiBase.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    AdminUserModel(
                        id="admin-1",
                        username="admin",
                        normalized_username="ADMIN",
                        password_hash=hash_password("secret"),
                        display_name="Admin",
                    ),
                    AdminRoleModel(
                        id="role-1",
                        role_code="org_reader",
                        role_name="Organization Reader",
                    ),
                    AdminPermissionModel(
                        id="permission-1",
                        permission_code="org.view",
                        permission_name="View organization",
                        module="org",
                    ),
                    AdminRolePermissionModel(
                        id="role-permission-1",
                        role_id="role-1",
                        permission_id="permission-1",
                    ),
                    AdminTenantMemberModel(
                        id="member-1",
                        admin_user_id="admin-1",
                        tenant_id="tenant-1",
                    ),
                    AdminTenantRoleModel(
                        id="tenant-role-1",
                        tenant_member_id="member-1",
                        role_id="role-1",
                    ),
                    AdminTenantScopeModel(
                        id="tenant-scope-1",
                        tenant_member_id="member-1",
                        scope_type="tenant",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()


def _add_admin_permissions(project_home: Path, *permission_codes: str) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            for index, permission_code in enumerate(permission_codes, start=2):
                permission_id = f"permission-{index}"
                session.add_all(
                    [
                        AdminPermissionModel(
                            id=permission_id,
                            permission_code=permission_code,
                            permission_name=permission_code,
                            module=permission_code.split(".", 1)[0],
                        ),
                        AdminRolePermissionModel(
                            id=f"role-permission-{index}",
                            role_id="role-1",
                            permission_id=permission_id,
                        ),
                    ]
                )
            session.commit()
    finally:
        engine.dispose()


def _promote_admin_to_super(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            user = session.get(AdminUserModel, "admin-1")
            assert user is not None
            user.is_super = True
            session.commit()
    finally:
        engine.dispose()


def _seed_conflicting_admin(project_home: Path) -> None:
    engine = create_engine(f"sqlite:///{project_home / 'zhizhi.db'}")
    try:
        with Session(engine) as session:
            session.add(
                AdminUserModel(
                    id="admin-conflict",
                    username="conflict",
                    normalized_username="CONFLICT",
                    password_hash=hash_password("secret"),
                    display_name="Conflict",
                    phone="13900000000",
                    email="taken@example.com",
                )
            )
            session.commit()
    finally:
        engine.dispose()


def _app_with_default_settings(tmp_path: Path):
    bootstrap = BootstrapSettings(PROJECT_HOME=tmp_path)
    runtime = ZhizhiAdminApiRuntime(bootstrap, settings=AdminApiSettings())
    return create_admin_app(bootstrap=bootstrap, runtime=runtime)


def _admin_headers(runtime: ZhizhiAdminApiRuntime) -> dict[str, str]:
    security = runtime._iam.identity_security if runtime._iam is not None else None
    assert security is not None
    token = security.issue_admin_token(
        user_id="admin-1",
        username="admin",
        is_super=False,
    )
    csrf_token = "test-admin-csrf"
    return {
        "Cookie": (f"zhizhi_admin_session={token}; " f"zhizhi_admin_csrf={csrf_token}"),
        "X-CSRF-Token": csrf_token,
    }


def _write_private_key(project_home: Path) -> Path:
    path = project_home / "password.pem"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path


def _redis_settings() -> ZhizhiRedisSettings:
    return ZhizhiRedisSettings(
        enabled=True,
        connection=RedisConnectionSettings(
            mode=RedisMode.STANDALONE,
            host="redis.internal",
        ),
    )


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.initialized = False
        self.closed = False

    async def initialize(self) -> None:
        self.initialized = True

    async def close(self) -> None:
        self.initialized = False
        self.closed = True

    async def get(self, key: str) -> object:
        return self.values.get(key)

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> bool:
        del seconds
        return key in self.values

    async def ttl(self, key: str) -> int:
        return 30 if key in self.values else -2

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)


class _FailingSessionService:
    def __init__(self, *, kind: ApplicationErrorKind, detail: str) -> None:
        self._kind = kind
        self._detail = detail

    def decode_token(self, token: str) -> dict[str, object]:
        assert token == "syntactically-valid-test-token"
        return {"sub": "admin-1", "ver": 0}

    async def load_session(self, *, user_id: str, token_version: int) -> None:
        assert user_id == "admin-1"
        assert token_version == 0
        raise ApplicationError(self._kind, self._detail)


class _InvalidVersionSessionService:
    def __init__(self, token_version: object) -> None:
        self._token_version = token_version
        self.session_loaded = False

    def decode_token(self, token: str) -> dict[str, object]:
        assert token == "syntactically-valid-test-token"
        return {"sub": "admin-1", "ver": self._token_version}

    async def load_session(self, *, user_id: str, token_version: int) -> None:
        del user_id, token_version
        self.session_loaded = True
