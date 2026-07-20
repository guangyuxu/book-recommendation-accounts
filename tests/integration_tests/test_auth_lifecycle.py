"""End-to-end auth journey on real Postgres: signup -> login -> refresh rotation -> reuse -> logout.

Refresh tokens ride an HttpOnly cookie scoped to /auth. Because that cookie is `Secure` (not
auto-sent by the test client over http), each step reads the raw token from `Set-Cookie` and replays
it via an explicit `Cookie` header -- the same server path a browser exercises over https.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _refresh_cookie(resp: object) -> str:
    value = resp.cookies.get("refresh_token")  # type: ignore[attr-defined]
    assert value, "expected a refresh_token cookie"
    return value


def test_full_auth_lifecycle(auth: dict) -> None:
    client = auth["client"]

    # 1. Log in with the credentials created at signup -> a fresh access token + refresh cookie.
    login = client.post(
        "/auth/login",
        json={"email": "parent@example.com", "password": "s3cret-password"},
    )
    assert login.status_code == 200, login.text
    access = login.json()["access_token"]
    refresh = _refresh_cookie(login)

    # 2. The access token authenticates the external face and re-derives identity server-side.
    me = client.get("/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "parent@example.com"
    assert me.json()["family_id"] == auth["family_id"]

    # 3. Refresh rotates the cookie and mints a new, working access token.
    rotated = client.post(
        "/auth/refresh", headers={"Cookie": f"refresh_token={refresh}"}
    )
    assert rotated.status_code == 200, rotated.text
    new_refresh = _refresh_cookie(rotated)
    assert new_refresh != refresh
    new_access = rotated.json()["access_token"]
    assert (
        client.get("/me", headers={"Authorization": f"Bearer {new_access}"}).status_code
        == 200
    )

    # 4. Replaying the OLD (already-consumed) refresh token is theft -> the whole lineage burns.
    replay = client.post(
        "/auth/refresh", headers={"Cookie": f"refresh_token={refresh}"}
    )
    assert replay.status_code == 401
    after = client.post(
        "/auth/refresh", headers={"Cookie": f"refresh_token={new_refresh}"}
    )
    assert after.status_code == 401

    # 5. A brand-new login works and its cookie can be logged out, revoking that token.
    fresh_login = client.post(
        "/auth/login",
        json={"email": "parent@example.com", "password": "s3cret-password"},
    )
    fresh_refresh = _refresh_cookie(fresh_login)
    assert (
        client.post(
            "/auth/logout", headers={"Cookie": f"refresh_token={fresh_refresh}"}
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/auth/refresh", headers={"Cookie": f"refresh_token={fresh_refresh}"}
        ).status_code
        == 401
    )


def test_duplicate_email_is_conflict_then_login_still_works(client: object) -> None:
    payload = {"email": "dup@example.com", "password": "s3cret-password"}
    assert client.post("/auth/signup", json=payload).status_code == 201  # type: ignore[attr-defined]
    # A second signup with the same email hits the unique constraint -> 409 (not a 500).
    assert client.post("/auth/signup", json=payload).status_code == 409  # type: ignore[attr-defined]
    # The original account is intact and can still authenticate.
    assert client.post("/auth/login", json=payload).status_code == 200  # type: ignore[attr-defined]
