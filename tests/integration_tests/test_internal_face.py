"""End-to-end internal-face journey on real Postgres.

The internal face (`/internal/*`) is what the agent calls instead of writing the account tables
directly. It authenticates with `X-Service-Token` (not a user token) and takes `family_id` as a
parameter -- but it must STILL enforce ownership in depth, so a valid service token with the WRONG
family_id cannot reach another family's rows. This journey seeds via the internal face, reads the
data back on the external (user-token) face, pulls the context bundle the agent consumes, and proves
the cross-family guard.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.integration


def _second_family(client: Any) -> str:
    return str(
        client.post(
            "/auth/signup",
            json={"email": "other@example.com", "password": "s3cret-password"},
        ).json()["family_id"]
    )


def test_internal_writes_are_visible_and_family_scoped(
    auth: dict[str, Any], service_headers: dict[str, str]
) -> None:
    client, headers, family_id = auth["client"], auth["headers"], auth["family_id"]

    # No / wrong service token is rejected before any work happens.
    assert (
        client.post(
            f"/internal/children?family_id={family_id}", json={"display_name": "X"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"/internal/children?family_id={family_id}",
            headers={"X-Service-Token": "nope"},
            json={"display_name": "X"},
        ).status_code
        == 401
    )

    # Create a child via the internal face; it is visible on the external face with a seeded profile.
    child_id = client.post(
        f"/internal/children?family_id={family_id}",
        headers=service_headers,
        json={"display_name": "Zoe", "birth_date": "2016-05-01"},
    ).json()["id"]
    assert (
        client.get(f"/family/children/{child_id}", headers=headers).status_code == 200
    )
    assert (
        client.get(
            f"/family/children/{child_id}/reading-profile", headers=headers
        ).status_code
        == 200
    )

    # Internal updates to the child and its reading profile persist (JSONB interests round-trip).
    assert (
        client.patch(
            f"/internal/children/{child_id}?family_id={family_id}",
            headers=service_headers,
            json={"grade": "4"},
        ).json()["grade"]
        == "4"
    )
    up = client.put(
        f"/internal/children/{child_id}/reading-profile?family_id={family_id}",
        headers=service_headers,
        json={"cefr_level": "B1", "interests": ["dinosaurs"]},
    )
    assert up.status_code == 200
    assert up.json()["interests"] == ["dinosaurs"]

    # Internal member + profile + policy writes.
    member_id = client.post(
        f"/internal/members?family_id={family_id}",
        headers=service_headers,
        json={"display_name": "Grandpa", "role": "member"},
    ).json()["id"]
    prof = client.put(
        f"/internal/members/{member_id}/profile?family_id={family_id}",
        headers=service_headers,
        json={"communication_style": "warm", "concerns": ["screen time"]},
    )
    assert prof.status_code == 200
    assert prof.json()["communication_style"] == "warm"
    assert (
        client.post(
            f"/internal/policies?family_id={family_id}",
            headers=service_headers,
            json={"goals": ["read nightly"]},
        ).status_code
        == 201
    )

    # The context bundle the agent consumes reflects everything, with no secrets leaked.
    ctx = client.get(
        f"/internal/families/{family_id}/context", headers=service_headers
    ).json()
    assert set(ctx) == {"family", "members", "children", "policies"}
    assert ctx["family"]["id"] == family_id
    assert child_id in ctx["children"]
    assert (
        ctx["children"][child_id]["age"] >= 8
    )  # derived from birth_date, never stored
    assert len(ctx["policies"]) == 1
    assert all("password_hash" not in m for m in ctx["members"])

    # A valid service token but a FOREIGN family_id must not reach this family's child.
    other = _second_family(client)
    assert (
        client.patch(
            f"/internal/children/{child_id}?family_id={other}",
            headers=service_headers,
            json={"grade": "9"},
        ).status_code
        == 404
    )
    # ...and that other family's context never includes this family's child.
    ctx_other = client.get(
        f"/internal/families/{other}/context", headers=service_headers
    ).json()
    assert ctx_other["children"] == {}
