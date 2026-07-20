"""Family-invite flow: create/list/revoke, single-use, and cross-family isolation (CLAUDE.md)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from accounts.db import session_scope
from accounts.db.models.family import Family, FamilyInvite
from accounts.db.repositories import FamilyInviteRepository, FamilyRepository
from accounts.security import InviteCodec

hash_invite_code = InviteCodec().hash


def _signup(client: Any, email: str) -> dict[str, str]:
    resp = client.post(
        "/auth/signup", json={"email": email, "password": "s3cret-password"}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- repository-level isolation ---
def test_invite_get_in_family_is_cross_family_scoped() -> None:
    with session_scope() as session:
        fam_a = FamilyRepository(session=session).add(Family(family_name="A")).id
        fam_b = FamilyRepository(session=session).add(Family(family_name="B")).id
        invite = FamilyInviteRepository(session=session).add(
            FamilyInvite(family_id=fam_a, code_hash=hash_invite_code("code-a"))
        )
        invite_id = invite.id

    with session_scope() as session:
        repo = FamilyInviteRepository(session=session)
        assert repo.get_in_family(invite_id, fam_a) is not None
        # Family B must NOT reach family A's invite by id.
        assert repo.get_in_family(invite_id, fam_b) is None
        assert repo.list_active_for_family(fam_b) == []


def test_active_lookup_excludes_expired_and_accepted() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    with session_scope() as session:
        fam = FamilyRepository(session=session).add(Family(family_name="A")).id
        repo = FamilyInviteRepository(session=session)
        repo.add(
            FamilyInvite(
                family_id=fam, code_hash=hash_invite_code("expired"), expires_at=past
            )
        )
        repo.add(
            FamilyInvite(
                family_id=fam,
                code_hash=hash_invite_code("used"),
                accepted_at=datetime.now(UTC),
            )
        )
        repo.add(FamilyInvite(family_id=fam, code_hash=hash_invite_code("live")))

    with session_scope() as session:
        repo = FamilyInviteRepository(session=session)
        assert repo.get_active_by_code_hash(hash_invite_code("expired")) is None
        assert repo.get_active_by_code_hash(hash_invite_code("used")) is None
        assert repo.get_active_by_code_hash(hash_invite_code("live")) is not None
        assert len(repo.list_active_for_family(fam)) == 1


# --- endpoint-level behavior + isolation ---
def test_invite_create_list_revoke(auth: dict[str, Any]) -> None:
    client, headers = auth["client"], auth["headers"]
    created = client.post("/family/invites", headers=headers, json={"role": "member"})
    assert created.status_code == 201, created.text
    invite = created.json()
    assert invite["code"] and invite["role"] == "member"
    assert invite["family_id"] == auth["family_id"]

    listed = client.get("/family/invites", headers=headers).json()
    assert len(listed) == 1
    # The code (and its digest) must never be exposed via listing.
    assert "code" not in listed[0]
    assert "code_hash" not in listed[0]

    assert (
        client.delete(f"/family/invites/{invite['id']}", headers=headers).status_code
        == 204
    )
    assert client.get("/family/invites", headers=headers).json() == []


def test_cannot_revoke_or_see_another_familys_invite(client: Any) -> None:
    headers_a = _signup(client, "a@example.com")
    headers_b = _signup(client, "b@example.com")
    invite_id = client.post("/family/invites", headers=headers_a, json={}).json()["id"]

    # B cannot see A's invite, nor revoke it by id.
    assert client.get("/family/invites", headers=headers_b).json() == []
    assert (
        client.delete(f"/family/invites/{invite_id}", headers=headers_b).status_code
        == 404
    )
    # A still has it.
    assert len(client.get("/family/invites", headers=headers_a).json()) == 1
