from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gewu_core import StorageEncryptionSettings
from gewu_core.http import PasswordTransportSettings, RsaPasswordTransport
from zhizhi_admin_api.app import create_admin_app
from zhizhi_admin_api.runtime import ZhizhiAdminApiRuntime
from zhizhi_admin_api.settings import AdminApiBootstrapSettings, AdminApiSettings
from zhizhi_platform.iam import JwtSettings

BOOTSTRAP_TOKEN = "one-time-bootstrap-token-material-01"
JWT_KEY = "admin-bootstrap-jwt-key-material-000001"
STORAGE_KEY = "admin-bootstrap-storage-key-material-01"


def test_bootstrap_token_rejects_short_configured_values(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        AdminApiBootstrapSettings(
            PROJECT_HOME=tmp_path,
            ADMIN_BOOTSTRAP_TOKEN="short-token",
        )


def test_browser_bootstrap_initializes_super_admin_once(tmp_path: Path) -> None:
    key_path = _write_private_key(tmp_path)
    bootstrap = AdminApiBootstrapSettings(
        PROJECT_HOME=tmp_path,
        ADMIN_BOOTSTRAP_TOKEN=BOOTSTRAP_TOKEN,
        AUTO_CREATE_SCHEMA=True,
        ENFORCE_STRONG_SECRETS=True,
        ADMIN_REQUIRE_PASSWORD_TRANSPORT=True,
    )
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_KEY, leeway_seconds=0),
            storage_encryption=StorageEncryptionSettings(key=STORAGE_KEY),
            password_transport=PasswordTransportSettings(private_key_path=str(key_path)),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        initial = client.get("/api/admin/bootstrap/status")
        assert initial.status_code == 200
        assert initial.json() == {
            "state": "setup_required",
            "bootstrap_enabled": True,
        }

        transport = runtime.password_transport
        assert isinstance(transport, RsaPasswordTransport)
        wrong_token = client.post(
            "/api/admin/bootstrap",
            json={
                "bootstrap_token": "wrong-token",
                "username": "root",
                "display_name": "超级管理员",
                "encrypted_password": transport.encrypt_for_transport("strong-password"),
            },
        )
        assert wrong_token.status_code == 403

        initialized = client.post(
            "/api/admin/bootstrap",
            json={
                "bootstrap_token": BOOTSTRAP_TOKEN,
                "username": "root",
                "display_name": "超级管理员",
                "encrypted_password": transport.encrypt_for_transport("strong-password"),
            },
        )
        assert initialized.status_code == 200
        assert initialized.json() == {
            "state": "ready",
            "bootstrap_enabled": False,
        }
        assert client.get("/api/admin/bootstrap/status").json()["state"] == "ready"

        repeated = client.post(
            "/api/admin/bootstrap",
            json={
                "bootstrap_token": BOOTSTRAP_TOKEN,
                "username": "other",
                "display_name": "Other",
                "encrypted_password": transport.encrypt_for_transport("another-strong-password"),
            },
        )
        assert repeated.status_code == 409

        login = client.post(
            "/api/admin/auth/login",
            json={
                "username": "root",
                "encrypted_password": transport.encrypt_for_transport("strong-password"),
            },
        )
        assert login.status_code == 200
        assert login.json()["user"]["is_super"] is True


def test_browser_bootstrap_fails_closed_without_configured_token(tmp_path: Path) -> None:
    key_path = _write_private_key(tmp_path)
    bootstrap = AdminApiBootstrapSettings(
        PROJECT_HOME=tmp_path,
        AUTO_CREATE_SCHEMA=True,
        ENFORCE_STRONG_SECRETS=True,
        ADMIN_REQUIRE_PASSWORD_TRANSPORT=True,
    )
    runtime = ZhizhiAdminApiRuntime(
        bootstrap,
        settings=AdminApiSettings(
            jwt=JwtSettings(sk=JWT_KEY),
            storage_encryption=StorageEncryptionSettings(key=STORAGE_KEY),
            password_transport=PasswordTransportSettings(private_key_path=str(key_path)),
        ),
    )
    app = create_admin_app(bootstrap=bootstrap, runtime=runtime)

    with TestClient(app) as client:
        status = client.get("/api/admin/bootstrap/status")
        assert status.json() == {
            "state": "setup_required",
            "bootstrap_enabled": False,
        }
        response = client.post(
            "/api/admin/bootstrap",
            json={
                "bootstrap_token": "unconfigured",
                "username": "root",
                "display_name": "超级管理员",
                "encrypted_password": "ciphertext",
            },
        )

    assert response.status_code == 503


def _write_private_key(project_home: Path) -> Path:
    path = project_home / "admin-password-key.pem"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path
