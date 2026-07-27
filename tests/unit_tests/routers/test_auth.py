"""Signup / login / identity endpoints — the RS256 issue-then-verify path."""

from __future__ import annotations

from typing import Any


def test_signup_creates_family_and_primary_member(client: Any) -> None:
    resp = client.post(
        "/auth/signup",
        json={"email": "A@Example.com ", "password": "s3cret-password"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["family_id"] and body["family_member_id"]

    # The issued token verifies on the same service (/me re-derives identity from it).
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    members = client.get("/family/members", headers=headers).json()
    assert len(members) == 1
    assert members[0]["is_primary_user"] is True
    assert members[0]["email"] == "a@example.com"


def test_signup_never_returns_password_hash(client: Any) -> None:
    resp = client.post(
        "/auth/signup",
        json={"email": "b@example.com", "password": "s3cret-password"},
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    members = client.get("/family/members", headers=headers).json()
    assert "password_hash" not in members[0]


def test_duplicate_email_conflicts(client: Any) -> None:
    payload = {"email": "dup@example.com", "password": "s3cret-password"}
    assert client.post("/auth/signup", json=payload).status_code == 201
    resp = client.post("/auth/signup", json=payload)
    assert resp.status_code == 409


def test_login_returns_token(client: Any) -> None:
    client.post(
        "/auth/signup",
        json={"email": "c@example.com", "password": "s3cret-password"},
    )
    ok = client.post(
        "/auth/login",
        json={"email": "c@example.com", "password": "s3cret-password"},
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = client.post(
        "/auth/login", json={"email": "c@example.com", "password": "wrong"}
    )
    assert bad.status_code == 401


def test_login_unknown_email_is_401(client: Any) -> None:
    resp = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever00"}
    )
    assert resp.status_code == 401


def test_me_requires_valid_bearer(client: Any) -> None:
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Basic x"}).status_code == 401
    # A syntactically-bearer but bogus token fails signature verification.
    assert (
        client.get("/me", headers={"Authorization": "Bearer not.a.jwt"}).status_code
        == 401
    )


def test_me_echoes_verified_token_identity(auth: dict[str, Any]) -> None:
    resp = auth["client"].get("/me", headers=auth["headers"])
    assert resp.status_code == 200
    assert resp.json()["family_id"] == auth["family_id"]


def test_signup_with_invite_joins_existing_family(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]
    code = client.post(
        "/family/invites", headers=headers, json={"role": "parent"}
    ).json()["code"]

    resp = client.post(
        "/auth/signup",
        json={
            "email": "second@example.com",
            "password": "s3cret-password",
            "display_name": "Second",
            "invite_code": code,
        },
    )
    assert resp.status_code == 201, resp.text
    joined = resp.json()
    # Same family, distinct member.
    assert joined["family_id"] == auth["family_id"]
    assert joined["family_member_id"] != auth["family_member_id"]

    members = client.get("/family/members", headers=headers).json()
    assert len(members) == 2
    new_member = next(m for m in members if m["email"] == "second@example.com")
    assert new_member["is_primary_user"] is False
    assert new_member["role"] == "parent"  # role comes from the invite


def test_signup_with_bad_invite_is_400(client: Any) -> None:
    resp = client.post(
        "/auth/signup",
        json={
            "email": "x@example.com",
            "password": "s3cret-password",
            "invite_code": "not-a-real-code",
        },
    )
    assert resp.status_code == 400


def test_invite_is_single_use(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]
    code = client.post("/family/invites", headers=headers, json={}).json()["code"]

    first = client.post(
        "/auth/signup",
        json={
            "email": "one@example.com",
            "password": "s3cret-password",
            "invite_code": code,
        },
    )
    assert first.status_code == 201
    # Reusing the same (now accepted) code is rejected.
    second = client.post(
        "/auth/signup",
        json={
            "email": "two@example.com",
            "password": "s3cret-password",
            "invite_code": code,
        },
    )
    assert second.status_code == 400
