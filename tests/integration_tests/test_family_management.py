"""End-to-end family-management journey on real Postgres.

A parent signs up, renames the family, adds a second member, creates a child with a reading
profile, sets a reading policy, and reads it all back -- asserting each write persists across
requests (i.e. was committed to Postgres, not just held in a session). A final step proves a second
family cannot reach the first family's child by id (CLAUDE.md cross-family isolation).
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


def test_family_management_full_chain(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]

    # Family starts with exactly the primary member from signup.
    assert client.get("/family", headers=headers).json()["id"] == auth["family_id"]
    assert len(client.get("/family/members", headers=headers).json()) == 1

    # Rename the family; the change is readable back.
    renamed = client.patch(
        "/family", headers=headers, json={"family_name": "The Readers"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["family_name"] == "The Readers"
    assert client.get("/family", headers=headers).json()["family_name"] == "The Readers"

    # Add a second member.
    member = client.post(
        "/family/members",
        headers=headers,
        json={"display_name": "Sibling", "role": "child"},
    )
    assert member.status_code == 201, member.text
    assert len(client.get("/family/members", headers=headers).json()) == 2

    # Create a child; a reading profile is seeded alongside it.
    child = client.post(
        "/family/children",
        headers=headers,
        json={"display_name": "Ada", "gender": "Female", "birth_date": "2016-05-01"},
    )
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]
    assert (
        client.get(
            f"/family/children/{child_id}/reading-profile", headers=headers
        ).status_code
        == 200
    )

    # Upsert the reading profile -- JSONB `interests` array round-trips through Postgres.
    profile = client.put(
        f"/family/children/{child_id}/reading-profile",
        headers=headers,
        json={"cefr_level": "A2", "interests": ["space", "dinosaurs"]},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["cefr_level"] == "A2"
    assert profile.json()["interests"] == ["space", "dinosaurs"]

    # Patch a scalar child field.
    assert (
        client.patch(
            f"/family/children/{child_id}", headers=headers, json={"grade": "3"}
        ).json()["grade"]
        == "3"
    )

    # A family-wide reading policy persists and lists back.
    policy = client.post(
        "/family/policies",
        headers=headers,
        json={"goals": ["read daily"], "avoid_topics": ["violence"]},
    )
    assert policy.status_code == 201, policy.text
    policies = client.get("/family/policies", headers=headers).json()
    assert len(policies) == 1
    assert policies[0]["id"] == policy.json()["id"]

    # Delete the child; it and its reading profile become unreachable.
    assert (
        client.delete(f"/family/children/{child_id}", headers=headers).status_code
        == 204
    )
    assert (
        client.get(f"/family/children/{child_id}", headers=headers).status_code == 404
    )
    assert client.get("/family/children", headers=headers).json() == []


def test_second_family_cannot_reach_first_familys_child(client: Any) -> None:
    headers_a = _signup(client, "a@example.com")
    headers_b = _signup(client, "b@example.com")
    child_id = client.post(
        "/family/children", headers=headers_a, json={"display_name": "Kid"}
    ).json()["id"]

    # Family B is scoped to its own family_id server-side -> A's child reads as 404 for B.
    assert (
        client.get(f"/family/children/{child_id}", headers=headers_b).status_code == 404
    )
    assert (
        client.patch(
            f"/family/children/{child_id}", headers=headers_b, json={"grade": "9"}
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/family/children/{child_id}", headers=headers_b).status_code
        == 404
    )
    # Family A still owns it.
    assert (
        client.get(f"/family/children/{child_id}", headers=headers_a).status_code == 200
    )
