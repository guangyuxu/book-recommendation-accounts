"""Integration-test setup: full HTTP business flows against a REAL ephemeral Postgres.

Where `tests/unit_tests` runs on a temp SQLite file (fast, offline, but only an approximation of
the production DB), these tests run against a throwaway Postgres cluster started by
pytest-postgresql. That cluster is spun up locally via `initdb`/`pg_ctl` in a temp dir on a random
port -- so it is still OFFLINE (no Docker, no network), it just requires the Postgres binaries on
PATH. Running against real Postgres exercises what SQLite cannot: JSONB / `text[]` column types,
server defaults (`gen_random_uuid()`, `now()`), real CHECK-constraint enums, and true
transaction/rollback semantics.

The engine seam:  `accounts.db.base` builds its engine from `DATABASE_URL` at IMPORT time, but the
throwaway cluster's port is only known once pytest-postgresql has started it. So a session-scoped
fixture (1) points `DATABASE_URL` at a dedicated database on that cluster and (2) rebuilds and
rebinds the engine / sessionmaker BEFORE the app is first imported. `accounts.providers` reads
`SessionLocal` off `accounts.db` when the app is built (inside the `client` fixture), which happens
after this rebind -- so both the app and direct `session_scope()` seeding share the one test engine.

RS256 keypair + service token mirror the unit-test setup so the REAL token path is exercised.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pytest_postgresql import factories

SERVICE_TOKEN = "test-service-token"
# A dedicated database on the throwaway cluster, distinct from pytest-postgresql's own template db.
_TEST_DB = "accounts_it"


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


# Static secrets can be set at import time (the port cannot -- see `_bind_engine`). `setdefault`
# lets CI export its own values.
_priv, _pub = make_keypair()
os.environ.setdefault("JWT_PRIVATE_KEY", _priv)
os.environ.setdefault("JWT_PUBLIC_KEY", _pub)
os.environ.setdefault("ACCOUNTS_SERVICE_TOKEN", SERVICE_TOKEN)

# Pin the cluster to TCP on 127.0.0.1 so we get a clean host:port SQLAlchemy URL (the default host
# is a unix-socket directory, awkward to express as a driver URL).
postgresql_proc = factories.postgresql_proc(host="127.0.0.1")


@pytest.fixture(scope="session")
def _database_url(postgresql_proc: Any) -> str:
    """Create a dedicated database on the throwaway cluster and return its SQLAlchemy URL."""
    import psycopg

    proc = postgresql_proc
    admin = (
        f"host={proc.host} port={proc.port} user={proc.user} "
        f"password={proc.password or ''} dbname={proc.template_dbname}"
    )
    with psycopg.connect(admin, autocommit=True) as conn:
        # DROP first so a crashed prior run in the same cluster can't wedge us.
        conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB}"')
        conn.execute(f'CREATE DATABASE "{_TEST_DB}"')

    pw = f":{proc.password}" if proc.password else ""
    return f"postgresql+psycopg://{proc.user}{pw}@{proc.host}:{proc.port}/{_TEST_DB}"


@pytest.fixture(scope="session", autouse=True)
def _bind_engine(_database_url: str) -> Iterator[None]:
    """Point the app at the throwaway Postgres by rebuilding + rebinding the engine before import."""
    os.environ["DATABASE_URL"] = _database_url

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import accounts.db as dbpkg
    import accounts.db.base as base

    engine = create_engine(_database_url, future=True, pool_pre_ping=True)
    maker = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    # Rebind on the defining module (so `session_scope`/`init_db`, which look up module globals at
    # call time, use it) and on the `accounts.db` package (so `providers` picks it up on app build).
    base.engine = engine
    base.SessionLocal = maker
    base.DATABASE_URL = _database_url
    base._is_sqlite = False
    base._schema = None
    dbpkg.engine = engine
    dbpkg.SessionLocal = maker

    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _fresh_db() -> Iterator[None]:
    """Recreate all tables before each test for isolation (mirrors the unit-test fixture)."""
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
