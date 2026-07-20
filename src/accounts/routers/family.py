"""Family / member / child / reading-profile / policy management (external face).

Thin adapters over the shared service layer: each handler derives `family_id` from the verified
token (the injected `Identity`) and forwards to a service, which scopes every read/write to that
`family_id` (via `get_in_family(...)`), so a caller can never reach another family's data by passing
a foreign id. Any authenticated member may manage the whole family's records. The services are the
SAME ones the internal face uses; only the identity source differs.
"""

from __future__ import annotations

import uuid
from typing import Any

from dishka.integrations.fastapi import DishkaSyncRoute, FromDishka
from fastapi import APIRouter, Depends, status

from ..auth import Identity, bearer_scheme
from ..schemas import (
    ChildCreate,
    ChildUpdate,
    FamilyUpdate,
    InviteCreate,
    InviteResponse,
    MemberCreate,
    MemberProfileUpsert,
    MemberUpdate,
    PolicyCreate,
    PolicyUpdate,
    ReadingHistoryCreate,
    ReadingHistoryUpdate,
    ReadingProfileUpsert,
)
from ..services import (
    ChildService,
    FamilyService,
    InviteService,
    MemberService,
    PolicyService,
)

router = APIRouter(
    prefix="/family",
    tags=["family"],
    route_class=DishkaSyncRoute,
    # Doc-only: surfaces the Bearer requirement (and Authorize button) in Swagger for every route
    # here. Enforcement stays in the injected `Identity` / `BearerIdentityResolver` (see ..auth).
    dependencies=[Depends(bearer_scheme)],
)


def _fid(identity: Identity) -> uuid.UUID:
    return uuid.UUID(identity.family_id)


# --- family ---
@router.get("")
def get_family(
    svc: FromDishka[FamilyService], identity: FromDishka[Identity]
) -> dict[str, Any]:
    return svc.get(_fid(identity))


@router.patch("")
def update_family(
    body: FamilyUpdate, svc: FromDishka[FamilyService], identity: FromDishka[Identity]
) -> dict[str, Any]:
    return svc.update(_fid(identity), body)


# --- members ---
@router.get("/members")
def list_members(
    svc: FromDishka[MemberService], identity: FromDishka[Identity]
) -> list[dict[str, Any]]:
    return svc.list(_fid(identity))


@router.post("/members", status_code=status.HTTP_201_CREATED)
def create_member(
    body: MemberCreate, svc: FromDishka[MemberService], identity: FromDishka[Identity]
) -> dict[str, Any]:
    return svc.create(_fid(identity), body)


@router.get("/members/{member_id}")
def get_member(
    member_id: uuid.UUID, svc: FromDishka[MemberService], identity: FromDishka[Identity]
) -> dict[str, Any]:
    return svc.get(_fid(identity), member_id)


@router.patch("/members/{member_id}")
def update_member(
    member_id: uuid.UUID,
    body: MemberUpdate,
    svc: FromDishka[MemberService],
    identity: FromDishka[Identity],
) -> dict[str, Any]:
    return svc.update(_fid(identity), member_id, body)


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    member_id: uuid.UUID, svc: FromDishka[MemberService], identity: FromDishka[Identity]
) -> None:
    svc.delete(_fid(identity), member_id)


@router.get("/members/{member_id}/profile")
def get_member_profile(
    member_id: uuid.UUID, svc: FromDishka[MemberService], identity: FromDishka[Identity]
) -> dict[str, Any]:
    return svc.get_profile(_fid(identity), member_id)


@router.put("/members/{member_id}/profile")
def upsert_member_profile(
    member_id: uuid.UUID,
    body: MemberProfileUpsert,
    svc: FromDishka[MemberService],
    identity: FromDishka[Identity],
) -> dict[str, Any]:
    return svc.upsert_profile(_fid(identity), member_id, body)


# --- invites (second-member join flow) ---
@router.post(
    "/invites", response_model=InviteResponse, status_code=status.HTTP_201_CREATED
)
def create_invite(
    body: InviteCreate, svc: FromDishka[InviteService], identity: FromDishka[Identity]
) -> InviteResponse:
    """Create a single-use invite for the caller's family; the raw code is returned only here."""
    return svc.create(_fid(identity), uuid.UUID(identity.family_member_id), body)


@router.get("/invites")
def list_invites(
    svc: FromDishka[InviteService], identity: FromDishka[Identity]
) -> list[dict[str, Any]]:
    """List the family's active (unredeemed, unexpired) invites; codes are never returned."""
    return svc.list(_fid(identity))


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    invite_id: uuid.UUID, svc: FromDishka[InviteService], identity: FromDishka[Identity]
) -> None:
    svc.revoke(_fid(identity), invite_id)


# --- children ---
@router.get("/children")
def list_children(
    svc: FromDishka[ChildService], identity: FromDishka[Identity]
) -> list[dict[str, Any]]:
    return svc.list(_fid(identity))


@router.post("/children", status_code=status.HTTP_201_CREATED)
def create_child(
    body: ChildCreate, svc: FromDishka[ChildService], identity: FromDishka[Identity]
) -> dict[str, Any]:
    return svc.create(_fid(identity), body)


@router.get("/children/{child_id}")
def get_child(
    child_id: uuid.UUID, svc: FromDishka[ChildService], identity: FromDishka[Identity]
) -> dict[str, Any]:
    return svc.get(_fid(identity), child_id)


@router.patch("/children/{child_id}")
def update_child(
    child_id: uuid.UUID,
    body: ChildUpdate,
    svc: FromDishka[ChildService],
    identity: FromDishka[Identity],
) -> dict[str, Any]:
    return svc.update(_fid(identity), child_id, body)


@router.delete("/children/{child_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_child(
    child_id: uuid.UUID, svc: FromDishka[ChildService], identity: FromDishka[Identity]
) -> None:
    svc.delete(_fid(identity), child_id)


# --- child reading profile ---
@router.get("/children/{child_id}/reading-profile")
def get_reading_profile(
    child_id: uuid.UUID, svc: FromDishka[ChildService], identity: FromDishka[Identity]
) -> dict[str, Any]:
    return svc.get_reading_profile(_fid(identity), child_id)


@router.put("/children/{child_id}/reading-profile")
def upsert_reading_profile(
    child_id: uuid.UUID,
    body: ReadingProfileUpsert,
    svc: FromDishka[ChildService],
    identity: FromDishka[Identity],
) -> dict[str, Any]:
    return svc.upsert_reading_profile(_fid(identity), child_id, body)


# --- child reading history (a list of books) ---
@router.get("/children/{child_id}/reading-history")
def list_reading_history(
    child_id: uuid.UUID, svc: FromDishka[ChildService], identity: FromDishka[Identity]
) -> list[dict[str, Any]]:
    return svc.list_reading_history(_fid(identity), child_id)


@router.post(
    "/children/{child_id}/reading-history", status_code=status.HTTP_201_CREATED
)
def create_reading_history(
    child_id: uuid.UUID,
    body: ReadingHistoryCreate,
    svc: FromDishka[ChildService],
    identity: FromDishka[Identity],
) -> dict[str, Any]:
    return svc.add_reading_history(_fid(identity), child_id, body)


@router.patch("/children/{child_id}/reading-history/{entry_id}")
def update_reading_history(
    child_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: ReadingHistoryUpdate,
    svc: FromDishka[ChildService],
    identity: FromDishka[Identity],
) -> dict[str, Any]:
    return svc.update_reading_history(_fid(identity), child_id, entry_id, body)


@router.delete(
    "/children/{child_id}/reading-history/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_reading_history(
    child_id: uuid.UUID,
    entry_id: uuid.UUID,
    svc: FromDishka[ChildService],
    identity: FromDishka[Identity],
) -> None:
    svc.delete_reading_history(_fid(identity), child_id, entry_id)


# --- reading policies ---
@router.get("/policies")
def list_policies(
    svc: FromDishka[PolicyService], identity: FromDishka[Identity]
) -> list[dict[str, Any]]:
    return svc.list(_fid(identity))


@router.post("/policies", status_code=status.HTTP_201_CREATED)
def create_policy(
    body: PolicyCreate, svc: FromDishka[PolicyService], identity: FromDishka[Identity]
) -> dict[str, Any]:
    return svc.create(_fid(identity), body)


@router.patch("/policies/{policy_id}")
def update_policy(
    policy_id: uuid.UUID,
    body: PolicyUpdate,
    svc: FromDishka[PolicyService],
    identity: FromDishka[Identity],
) -> dict[str, Any]:
    return svc.update(_fid(identity), policy_id, body)


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(
    policy_id: uuid.UUID, svc: FromDishka[PolicyService], identity: FromDishka[Identity]
) -> None:
    svc.delete(_fid(identity), policy_id)
