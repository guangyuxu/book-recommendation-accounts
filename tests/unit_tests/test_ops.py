"""Cross-cutting ops: health, readiness, error envelope, correlation id, and settings parsing."""

from __future__ import annotations

from typing import Any

from accounts.config import Settings


def test_healthz(client: Any) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_ok_with_sqlite(client: Any) -> None:
    # The test sqlite DB is reachable, so readiness is ok.
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"db": True}}


def test_error_envelope_shape(client: Any) -> None:
    resp = client.get("/me")  # no token -> 401 through the envelope handler
    assert resp.status_code == 401
    err = resp.json()["error"]
    assert err["code"] == 401
    assert "request_id" in err
    assert err["request_id"] == resp.headers["X-Request-Id"]


def test_correlation_id_is_echoed(client: Any) -> None:
    resp = client.get("/healthz", headers={"X-Request-Id": "trace-123"})
    assert resp.headers["X-Request-Id"] == "trace-123"


def test_correlation_id_is_generated_when_absent(client: Any) -> None:
    resp = client.get("/healthz")
    assert resp.headers.get("X-Request-Id")


def test_cors_origin_list_parsing() -> None:
    s = Settings(  # type: ignore[call-arg]
        cors_origins="http://a.com, http://b.com ,",
        jwt_private_key="x",
        jwt_public_key="y",
        service_token="z",
    )
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]
