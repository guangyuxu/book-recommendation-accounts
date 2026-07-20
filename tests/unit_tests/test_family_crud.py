"""Family / member / child / reading-profile / policy CRUD, incl. cross-family isolation."""

from __future__ import annotations

from typing import Any


def _signup(client: Any, email: str) -> dict[str, str]:
    resp = client.post(
        "/auth/signup", json={"email": email, "password": "s3cret-password"}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_family_get_and_update(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]
    fam = client.get("/family", headers=headers).json()
    assert fam["id"] == auth["family_id"]
    updated = client.patch(
        "/family", headers=headers, json={"family_name": "New Name"}
    ).json()
    assert updated["family_name"] == "New Name"


def test_child_crud_lifecycle(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]
    created = client.post(
        "/family/children",
        headers=headers,
        json={"display_name": "Ada", "gender": "Female", "birth_date": "2016-05-01"},
    )
    assert created.status_code == 201, created.text
    child = created.json()
    child_id = child["id"]
    assert child["display_name"] == "Ada"

    # A reading profile was seeded with the child.
    prof = client.get(f"/family/children/{child_id}/reading-profile", headers=headers)
    assert prof.status_code == 200

    # Update + upsert the reading profile.
    up = client.put(
        f"/family/children/{child_id}/reading-profile",
        headers=headers,
        json={"cefr_level": "A2", "interests": ["space"]},
    ).json()
    assert up["cefr_level"] == "A2"
    assert up["interests"] == ["space"]

    assert (
        client.patch(
            f"/family/children/{child_id}", headers=headers, json={"grade": "3"}
        ).json()["grade"]
        == "3"
    )
    assert len(client.get("/family/children", headers=headers).json()) == 1
    assert (
        client.delete(f"/family/children/{child_id}", headers=headers).status_code
        == 204
    )
    assert (
        client.get(f"/family/children/{child_id}", headers=headers).status_code == 404
    )


def test_reading_history_crud(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]
    child_id = client.post(
        "/family/children", headers=headers, json={"display_name": "Ada"}
    ).json()["id"]

    # Empty to start.
    assert (
        client.get(
            f"/family/children/{child_id}/reading-history", headers=headers
        ).json()
        == []
    )

    created = client.post(
        f"/family/children/{child_id}/reading-history",
        headers=headers,
        json={"title": "Frog and Toad", "liked": True, "reasons": ["funny"]},
    )
    assert created.status_code == 201, created.text
    entry = created.json()
    entry_id = entry["id"]
    assert entry["title"] == "Frog and Toad"
    assert entry["reasons"] == ["funny"]

    # Update.
    up = client.patch(
        f"/family/children/{child_id}/reading-history/{entry_id}",
        headers=headers,
        json={"status": "finished", "finished_at": "2026-01-15"},
    )
    assert up.status_code == 200
    assert up.json()["status"] == "finished"
    assert up.json()["title"] == "Frog and Toad"  # preserved

    # List shows the one entry, then delete.
    assert (
        len(
            client.get(
                f"/family/children/{child_id}/reading-history", headers=headers
            ).json()
        )
        == 1
    )
    assert (
        client.delete(
            f"/family/children/{child_id}/reading-history/{entry_id}", headers=headers
        ).status_code
        == 204
    )
    assert (
        client.get(
            f"/family/children/{child_id}/reading-history", headers=headers
        ).json()
        == []
    )


def test_reading_history_cross_family_isolation(client: Any) -> None:
    headers_a = _signup(client, "rh-a@example.com")
    headers_b = _signup(client, "rh-b@example.com")
    child_id = client.post(
        "/family/children", headers=headers_a, json={"display_name": "Kid A"}
    ).json()["id"]
    entry_id = client.post(
        f"/family/children/{child_id}/reading-history",
        headers=headers_a,
        json={"title": "Secret Book"},
    ).json()["id"]

    # Family B cannot list, add, update, or delete family A's child's history.
    assert (
        client.get(
            f"/family/children/{child_id}/reading-history", headers=headers_b
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/family/children/{child_id}/reading-history",
            headers=headers_b,
            json={"title": "Injected"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/family/children/{child_id}/reading-history/{entry_id}",
            headers=headers_b,
            json={"title": "Hacked"},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/family/children/{child_id}/reading-history/{entry_id}",
            headers=headers_b,
        ).status_code
        == 404
    )


def test_member_crud_and_primary_delete_guard(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]
    # The primary member cannot be deleted.
    primary_id = auth["family_member_id"]
    assert (
        client.delete(f"/family/members/{primary_id}", headers=headers).status_code
        == 409
    )
    # Add and remove a secondary member.
    created = client.post(
        "/family/members",
        headers=headers,
        json={"display_name": "Sibling", "role": "child"},
    )
    assert created.status_code == 201
    member_id = created.json()["id"]
    assert (
        client.delete(f"/family/members/{member_id}", headers=headers).status_code
        == 204
    )


def test_member_profile_upsert_and_get(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]
    created = client.post(
        "/family/members",
        headers=headers,
        json={"display_name": "Parent Two", "role": "parent"},
    )
    assert created.status_code == 201
    member_id = created.json()["id"]

    # No profile yet -> 404 (the UI treats this as an empty form).
    assert (
        client.get(f"/family/members/{member_id}/profile", headers=headers).status_code
        == 404
    )

    # Upsert creates the 1:1 profile row.
    up = client.put(
        f"/family/members/{member_id}/profile",
        headers=headers,
        json={
            "occupation_background": "engineer",
            "concerns": ["screen time"],
            "confidence": 0.8,
        },
    )
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["occupation_background"] == "engineer"
    assert body["concerns"] == ["screen time"]

    # A second upsert updates the same row, and GET now returns it.
    client.put(
        f"/family/members/{member_id}/profile",
        headers=headers,
        json={"education_background": "MSc"},
    )
    got = client.get(f"/family/members/{member_id}/profile", headers=headers)
    assert got.status_code == 200
    assert got.json()["education_background"] == "MSc"
    # The earlier value is preserved across the partial upsert.
    assert got.json()["occupation_background"] == "engineer"


def test_member_profile_cross_family_isolation(client: Any) -> None:
    headers_a = _signup(client, "prof-a@example.com")
    headers_b = _signup(client, "prof-b@example.com")
    member_id = client.post(
        "/family/members", headers=headers_a, json={"display_name": "A Parent"}
    ).json()["id"]

    # Family B cannot read or write family A's member profile.
    assert (
        client.get(
            f"/family/members/{member_id}/profile", headers=headers_b
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/family/members/{member_id}/profile",
            headers=headers_b,
            json={"occupation_background": "x"},
        ).status_code
        == 404
    )


def test_policy_crud_and_bad_child_ref(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]
    created = client.post(
        "/family/policies",
        headers=headers,
        json={"goals": ["read daily"], "avoid_topics": ["violence"]},
    )
    assert created.status_code == 201
    policy_id = created.json()["id"]
    assert client.get("/family/policies", headers=headers).json()[0]["id"] == policy_id
    assert (
        client.patch(
            f"/family/policies/{policy_id}", headers=headers, json={"notes": "x"}
        ).json()["notes"]
        == "x"
    )
    assert (
        client.delete(f"/family/policies/{policy_id}", headers=headers).status_code
        == 204
    )
    # A policy referencing a non-existent child is rejected.
    bad = client.post(
        "/family/policies",
        headers=headers,
        json={"child_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert bad.status_code == 404


def test_cannot_reach_another_familys_child(client: Any) -> None:
    # Family A owns a child; family B must not read/update/delete it by id.
    headers_a = _signup(client, "a@example.com")
    headers_b = _signup(client, "b@example.com")
    child_id = client.post(
        "/family/children", headers=headers_a, json={"display_name": "Kid"}
    ).json()["id"]

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
    # Family A still sees it.
    assert (
        client.get(f"/family/children/{child_id}", headers=headers_a).status_code == 200
    )
