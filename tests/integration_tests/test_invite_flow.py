"""End-to-end invite journey on real Postgres: create -> join via signup -> single-use enforcement.

A parent mints an invite, a new user signs up with that code and lands in the SAME family (as a
distinct member with the invite's role), and the now-accepted code cannot be reused. A final step
proves a second family can neither see nor revoke the first family's invite.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.integration


def _signup(client: Any, email: str) -> dict[str, str]:
    token = client.post(
        "/auth/signup", json={"email": email, "password": "s3cret-password"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_invite_create_join_and_single_use(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]

    created = client.post("/family/invites", headers=headers, json={"role": "parent"})
    assert created.status_code == 201, created.text
    invite = created.json()
    code = invite["code"]
    assert invite["family_id"] == auth["family_id"]

    # Listing never exposes the code or its digest.
    listed = client.get("/family/invites", headers=headers).json()
    assert len(listed) == 1
    assert "code" not in listed[0] and "code_hash" not in listed[0]

    # A new user signs up with the code and joins the SAME family as a distinct member.
    joined = client.post(
        "/auth/signup",
        json={
            "email": "second@example.com",
            "password": "s3cret-password",
            "display_name": "Second",
            "invite_code": code,
        },
    )
    assert joined.status_code == 201, joined.text
    assert joined.json()["family_id"] == auth["family_id"]
    assert joined.json()["family_member_id"] != auth["family_member_id"]

    members = client.get("/family/members", headers=headers).json()
    assert len(members) == 2
    new_member = next(m for m in members if m["email"] == "second@example.com")
    assert new_member["is_primary_user"] is False
    assert new_member["role"] == "parent"  # role carried from the invite

    # The now-accepted code is single-use: a second signup with it is rejected.
    reused = client.post(
        "/auth/signup",
        json={
            "email": "third@example.com",
            "password": "s3cret-password",
            "invite_code": code,
        },
    )
    assert reused.status_code == 400


def test_invite_is_not_visible_or_revocable_across_families(client: Any) -> None:
    headers_a = _signup(client, "a@example.com")
    headers_b = _signup(client, "b@example.com")
    invite_id = client.post("/family/invites", headers=headers_a, json={}).json()["id"]

    # Family B sees none of A's invites and cannot revoke one by id.
    assert client.get("/family/invites", headers=headers_b).json() == []
    assert (
        client.delete(f"/family/invites/{invite_id}", headers=headers_b).status_code
        == 404
    )
    # Family A can revoke its own.
    assert (
        client.delete(f"/family/invites/{invite_id}", headers=headers_a).status_code
        == 204
    )
    assert client.get("/family/invites", headers=headers_a).json() == []
