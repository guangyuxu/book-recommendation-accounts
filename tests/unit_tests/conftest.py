"""Hermetic test setup: a shared file-backed sqlite DB, an ephemeral RS256 keypair, fixtures.

`accounts.db.base` builds its engine from `DATABASE_URL` at import time. We default it to
a temp *file* (not `:memory:`) so every connection opened per request shares one database — an
in-memory sqlite gives each connection its own empty DB, which would hide rows written by another
request.

This service is the token ISSUER, so tests need a real RS256 keypair: we generate one in-process and
export it inline via `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` (config resolves inline PEM before the file
path, so this wins over any local `keys/`). A service token is set so the internal face is enabled.
`setdefault` means CI's exported Postgres URL still wins.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

SERVICE_TOKEN = "test-service-token"


def make_keypair() -> tuple[str, str]:
    """Return a fresh (private_pem, public_pem) RS256 keypair as PEM strings."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_db_path}")

_priv, _pub = make_keypair()
os.environ.setdefault("JWT_PRIVATE_KEY", _priv)
os.environ.setdefault("JWT_PUBLIC_KEY", _pub)
os.environ.setdefault("ACCOUNTS_SERVICE_TOKEN", SERVICE_TOKEN)


@pytest.fixture(autouse=True)
def _fresh_db() -> Iterator[None]:
    """Recreate all tables before each test for isolation."""
    from accounts.db import Base, engine, init_db

    Base.metadata.drop_all(engine)
    init_db()
    yield


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    from accounts.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> Any:
    from fastapi.testclient import TestClient

    from accounts.main import create_app

    return TestClient(create_app())


@pytest.fixture
def service_headers() -> dict[str, str]:
    """Headers a trusted service (the agent) sends to reach the internal face."""
    return {"X-Service-Token": SERVICE_TOKEN}


@pytest.fixture
def auth(client: Any) -> dict[str, Any]:
    """Sign up a family and return the client, auth headers, and ids."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "parent@example.com",
            "password": "s3cret-password",
            "family_name": "Test Family",
            "display_name": "Parent",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {
        "client": client,
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "family_id": data["family_id"],
        "family_member_id": data["family_member_id"],
    }
