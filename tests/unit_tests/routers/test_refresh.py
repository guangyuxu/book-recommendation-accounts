"""Refresh-token flow: cookie issuance, rotation, reuse detection, logout, expiry, isolation.

Tokens are exchanged via an HttpOnly cookie scoped to /auth. Because that cookie is `Secure` by
default (not auto-sent by the test client over http), these tests read the raw token from the
`Set-Cookie` header and pass it explicitly on the next request — exercising the same server path a
browser would over https.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from accounts.db import session_scope
from accounts.db.models.family import Family, FamilyMember, RefreshToken
from accounts.db.repositories import (
    FamilyMemberRepository,
    FamilyRepository,
    RefreshTokenRepository,
)
from accounts.security import RefreshTokenCodec

_codec = RefreshTokenCodec()


def _signup(client: Any, email: str = "parent@example.com") -> Any:
    return client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": "s3cret-password",
            "family_name": "Test Family",
            "display_name": "Parent",
        },
    )


def _refresh_cookie(resp: Any) -> str:
    """Extract the raw refresh-token value from a response's Set-Cookie (parses regardless of Secure)."""
    value = resp.cookies.get("refresh_token")
    assert value, resp.headers.get("set-cookie")
    return value


# --- issuance / cookie attributes ---
def test_signup_sets_httponly_scoped_refresh_cookie(client: Any) -> None:
    resp = _signup(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Access token is in the body; the refresh token is NEVER in the body.
    assert body["access_token"]
    assert "refresh_token" not in body

    set_cookie = resp.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/auth" in set_cookie
    assert "Secure" in set_cookie  # default policy; local dev can disable via config


def test_login_sets_refresh_cookie(client: Any) -> None:
    _signup(client)
    resp = client.post(
        "/auth/login",
        json={"email": "parent@example.com", "password": "s3cret-password"},
    )
    assert resp.status_code == 200, resp.text
    assert _refresh_cookie(resp)


# --- rotation happy path ---
def test_refresh_rotates_and_new_access_token_works(client: Any) -> None:
    signup = _signup(client)
    old = _refresh_cookie(signup)

    rotated = client.post("/auth/refresh", headers={"Cookie": f"refresh_token={old}"})
    assert rotated.status_code == 200, rotated.text
    new_access = rotated.json()["access_token"]
    new_refresh = _refresh_cookie(rotated)
    assert new_refresh != old  # a genuinely new token was issued

    # The freshly minted access token authenticates against the external face.
    me = client.get("/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200, me.text


# --- reuse detection ---
def test_reuse_of_rotated_token_revokes_whole_session(client: Any) -> None:
    old = _refresh_cookie(_signup(client))

    rotated = client.post("/auth/refresh", headers={"Cookie": f"refresh_token={old}"})
    new = _refresh_cookie(rotated)

    # Replaying the OLD (already-consumed) token is treated as theft → 401.
    replay = client.post("/auth/refresh", headers={"Cookie": f"refresh_token={old}"})
    assert replay.status_code == 401, replay.text

    # ...and the whole lineage is burned: the NEW token no longer works either.
    after = client.post("/auth/refresh", headers={"Cookie": f"refresh_token={new}"})
    assert after.status_code == 401, after.text


def test_unknown_refresh_token_is_rejected(client: Any) -> None:
    resp = client.post(
        "/auth/refresh", headers={"Cookie": "refresh_token=not-a-real-token"}
    )
    assert resp.status_code == 401


def test_refresh_without_cookie_is_rejected(client: Any) -> None:
    assert client.post("/auth/refresh").status_code == 401


# --- logout ---
def test_logout_revokes_refresh_token(client: Any) -> None:
    raw = _refresh_cookie(_signup(client))

    logout = client.post("/auth/logout", headers={"Cookie": f"refresh_token={raw}"})
    assert logout.status_code == 204

    assert (
        client.post(
            "/auth/refresh", headers={"Cookie": f"refresh_token={raw}"}
        ).status_code
        == 401
    )


# --- expiry ---
def test_expired_refresh_token_is_rejected(client: Any) -> None:
    raw = "expired-refresh-token"
    past = datetime.now(UTC) - timedelta(seconds=1)
    with session_scope() as session:
        fam = FamilyRepository(session=session).add(Family(family_name="A")).id
        member = (
            FamilyMemberRepository(session=session)
            .add(FamilyMember(family_id=fam, role="parent"))
            .id
        )
        RefreshTokenRepository(session=session).add(
            RefreshToken(
                family_id=fam,
                family_member_id=member,
                session_id=uuid.uuid4(),
                token_hash=_codec.hash(raw),
                expires_at=past,
            )
        )

    assert (
        client.post(
            "/auth/refresh", headers={"Cookie": f"refresh_token={raw}"}
        ).status_code
        == 401
    )


# --- access-token path unaffected ---
def test_access_token_still_authenticates_family_face(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]
    assert client.get("/family/members", headers=headers).status_code == 200


# --- /me expansion (replaces an id token) ---
def test_me_returns_email_and_display_name(auth: dict[str, Any]) -> None:
    me = auth["client"].get("/me", headers=auth["headers"]).json()
    assert me["email"] == "parent@example.com"
    assert me["display_name"] == "Parent"
    assert me["family_id"] == auth["family_id"]
    assert me["family_member_id"] == auth["family_member_id"]


# --- repository-level cross-family isolation (CLAUDE.md) ---
def test_revoke_all_for_member_is_cross_family_scoped() -> None:
    future = datetime.now(UTC) + timedelta(days=1)
    with session_scope() as session:
        fam_a = FamilyRepository(session=session).add(Family(family_name="A")).id
        fam_b = FamilyRepository(session=session).add(Family(family_name="B")).id
        member = (
            FamilyMemberRepository(session=session)
            .add(FamilyMember(family_id=fam_a, role="parent"))
            .id
        )
        RefreshTokenRepository(session=session).add(
            RefreshToken(
                family_id=fam_a,
                family_member_id=member,
                session_id=uuid.uuid4(),
                token_hash=_codec.hash("tok"),
                expires_at=future,
            )
        )

    # Family B must NOT be able to revoke family A's member's tokens.
    with session_scope() as session:
        repo = RefreshTokenRepository(session=session)
        assert repo.revoke_all_for_member(member, fam_b) == 0
        assert repo.get_by_token_hash(_codec.hash("tok")).revoked_at is None

    # Family A can.
    with session_scope() as session:
        repo = RefreshTokenRepository(session=session)
        assert repo.revoke_all_for_member(member, fam_a) == 1
        assert repo.get_by_token_hash(_codec.hash("tok")).revoked_at is not None
