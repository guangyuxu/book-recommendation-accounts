"""Internal (service-to-service) face: service-token guard, writes, and cross-family isolation.

The internal face authenticates with `X-Service-Token`, not a user token, and takes `family_id` as
a parameter. It must STILL enforce ownership in depth (get_in_family), so a foreign `family_id`
cannot reach another family's rows even with a valid service token.
"""

from __future__ import annotations

from typing import Any

from accounts.config import Settings, get_settings

from ..conftest import make_keypair


def _second_family(client: Any) -> str:
    resp = client.post(
        "/auth/signup",
        json={"email": "other@example.com", "password": "s3cret-password"},
    )
    return str(resp.json()["family_id"])


def test_internal_requires_service_token(auth: dict[str, Any]) -> None:
    client, family_id = auth["client"], auth["family_id"]
    # No token, and a wrong token, are both rejected.
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


def test_internal_face_disabled_when_no_token_configured(auth: dict[str, Any]) -> None:
    client, family_id = auth["client"], auth["family_id"]
    priv, pub = make_keypair()
    # Settings with NO service token → the internal face fails closed (503), never open.
    no_token = Settings(  # type: ignore[call-arg]
        jwt_private_key=priv, jwt_public_key=pub, service_token=None
    )
    client.app.dependency_overrides[get_settings] = lambda: no_token
    try:
        resp = client.post(
            f"/internal/children?family_id={family_id}",
            headers={"X-Service-Token": "anything"},
            json={"display_name": "X"},
        )
        assert resp.status_code == 503
    finally:
        client.app.dependency_overrides.clear()


def test_internal_create_child_is_visible_on_external_face(
    auth: dict[str, Any], service_headers: dict[str, str]
) -> None:
    client, headers, family_id = auth["client"], auth["headers"], auth["family_id"]
    created = client.post(
        f"/internal/children?family_id={family_id}",
        headers=service_headers,
        json={"display_name": "Zoe"},
    )
    assert created.status_code == 201, created.text
    child_id = created.json()["id"]

    # The same child is reachable on the external (user-token) face, and its reading profile
    # was seeded by the internal create (mirroring the agent's create_child).
    got = client.get(f"/family/children/{child_id}", headers=headers)
    assert got.status_code == 200
    prof = client.get(f"/family/children/{child_id}/reading-profile", headers=headers)
    assert prof.status_code == 200


def test_internal_reading_profile_and_child_updates(
    auth: dict[str, Any], service_headers: dict[str, str]
) -> None:
    client, family_id = auth["client"], auth["family_id"]
    child_id = client.post(
        f"/internal/children?family_id={family_id}",
        headers=service_headers,
        json={"display_name": "Ada"},
    ).json()["id"]

    patched = client.patch(
        f"/internal/children/{child_id}?family_id={family_id}",
        headers=service_headers,
        json={"grade": "4"},
    )
    assert patched.status_code == 200
    assert patched.json()["grade"] == "4"

    up = client.put(
        f"/internal/children/{child_id}/reading-profile?family_id={family_id}",
        headers=service_headers,
        json={"cefr_level": "B1", "ar_level": 3.5, "interests": ["dinosaurs"]},
    )
    assert up.status_code == 200
    assert up.json()["cefr_level"] == "B1"
    assert float(up.json()["ar_level"]) == 3.5  # ar_level round-trips (agent writes it)


def test_internal_reading_history_crud(
    auth: dict[str, Any], service_headers: dict[str, str]
) -> None:
    client, family_id = auth["client"], auth["family_id"]
    child_id = client.post(
        f"/internal/children?family_id={family_id}",
        headers=service_headers,
        json={"display_name": "Leo"},
    ).json()["id"]

    # Empty to start.
    listing = client.get(
        f"/internal/children/{child_id}/reading-history?family_id={family_id}",
        headers=service_headers,
    )
    assert listing.status_code == 200
    assert listing.json() == []

    created = client.post(
        f"/internal/children/{child_id}/reading-history?family_id={family_id}",
        headers=service_headers,
        json={"title": "Dog Man", "status": "finished", "liked": True},
    )
    assert created.status_code == 201, created.text
    entry_id = created.json()["id"]
    assert created.json()["title"] == "Dog Man"

    patched = client.patch(
        f"/internal/children/{child_id}/reading-history/{entry_id}?family_id={family_id}",
        headers=service_headers,
        json={"status": "reading"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "reading"

    assert (
        len(
            client.get(
                f"/internal/children/{child_id}/reading-history?family_id={family_id}",
                headers=service_headers,
            ).json()
        )
        == 1
    )


def test_internal_reading_history_is_family_scoped(
    auth: dict[str, Any], service_headers: dict[str, str]
) -> None:
    # A valid service token with the WRONG family_id must not reach the child's history.
    client, family_id = auth["client"], auth["family_id"]
    child_id = client.post(
        f"/internal/children?family_id={family_id}",
        headers=service_headers,
        json={"display_name": "Kid"},
    ).json()["id"]
    other_family = _second_family(client)

    assert (
        client.get(
            f"/internal/children/{child_id}/reading-history?family_id={other_family}",
            headers=service_headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/internal/children/{child_id}/reading-history?family_id={other_family}",
            headers=service_headers,
            json={"title": "Sneaky", "status": "finished"},
        ).status_code
        == 404
    )


def test_internal_member_and_policy_writes(
    auth: dict[str, Any], service_headers: dict[str, str]
) -> None:
    client, family_id = auth["client"], auth["family_id"]
    member = client.post(
        f"/internal/members?family_id={family_id}",
        headers=service_headers,
        json={"display_name": "Grandpa", "role": "member"},
    )
    assert member.status_code == 201
    member_id = member.json()["id"]

    prof = client.put(
        f"/internal/members/{member_id}/profile?family_id={family_id}",
        headers=service_headers,
        json={"communication_style": "warm", "concerns": ["screen time"]},
    )
    assert prof.status_code == 200
    assert prof.json()["communication_style"] == "warm"

    policy = client.post(
        f"/internal/policies?family_id={family_id}",
        headers=service_headers,
        json={"goals": ["read nightly"]},
    )
    assert policy.status_code == 201


def test_internal_family_context_bundle(
    auth: dict[str, Any], service_headers: dict[str, str]
) -> None:
    client, headers, family_id = auth["client"], auth["headers"], auth["family_id"]
    # Seed a child (with a birth_date so age is derived) and a policy via the faces.
    child_id = client.post(
        "/family/children",
        headers=headers,
        json={"display_name": "Ada", "birth_date": "2016-05-01"},
    ).json()["id"]
    client.post("/family/policies", headers=headers, json={"goals": ["read nightly"]})

    resp = client.get(
        f"/internal/families/{family_id}/context", headers=service_headers
    )
    assert resp.status_code == 200, resp.text
    ctx = resp.json()

    # Same shape load_context expects.
    assert set(ctx) == {"family", "members", "children", "policies"}
    assert ctx["family"]["id"] == family_id
    assert len(ctx["members"]) == 1
    member = ctx["members"][0]
    assert member["is_primary_user"] is True
    assert member["profile"] == {}  # no member profile yet -> {}, not null
    assert "password_hash" not in member  # secrets never leak to the agent

    assert child_id in ctx["children"]
    child = ctx["children"][child_id]
    assert child["age"] == _age_from("2016-05-01")  # derived, never stored
    assert isinstance(child["reading_profile"], dict)  # seeded profile present
    assert len(ctx["policies"]) == 1


def test_internal_context_unknown_family_is_404(
    auth: dict[str, Any], service_headers: dict[str, str]
) -> None:
    client = auth["client"]
    missing = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"/internal/families/{missing}/context", headers=service_headers)
    assert resp.status_code == 404


def test_internal_context_requires_service_token(auth: dict[str, Any]) -> None:
    client, family_id = auth["client"], auth["family_id"]
    assert client.get(f"/internal/families/{family_id}/context").status_code == 401


def test_internal_context_is_family_scoped(
    auth: dict[str, Any], service_headers: dict[str, str]
) -> None:
    # Family A seeds a child; family B's context must not include it.
    client, headers = auth["client"], auth["headers"]
    client.post("/family/children", headers=headers, json={"display_name": "Kid"})
    family_b = _second_family(client)

    ctx_b = client.get(
        f"/internal/families/{family_b}/context", headers=service_headers
    ).json()
    assert ctx_b["children"] == {}
    assert ctx_b["family"]["id"] == family_b


def _age_from(iso: str) -> int:
    from datetime import date

    dob = date.fromisoformat(iso)
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def test_internal_foreign_family_id_cannot_reach_child(
    auth: dict[str, Any], service_headers: dict[str, str]
) -> None:
    client, family_id = auth["client"], auth["family_id"]
    child_id = client.post(
        f"/internal/children?family_id={family_id}",
        headers=service_headers,
        json={"display_name": "Kid"},
    ).json()["id"]

    other_family = _second_family(client)
    # A valid service token but the WRONG family_id must not reach the child (depth ownership).
    assert (
        client.patch(
            f"/internal/children/{child_id}?family_id={other_family}",
            headers=service_headers,
            json={"grade": "9"},
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/internal/children/{child_id}/reading-profile?family_id={other_family}",
            headers=service_headers,
            json={"cefr_level": "C1"},
        ).status_code
        == 404
    )
