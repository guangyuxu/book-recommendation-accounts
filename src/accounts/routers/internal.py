"""Internal (service-to-service) face for the agent — the write path that replaces direct DB writes.

Design (accounts is the single writer):

- Authentication is a SERVICE credential, not a user token: the caller (the agent) presents
  `X-Service-Token`, compared in constant time against `ACCOUNTS_SERVICE_TOKEN`. There is no user
  identity here; `family_id` / `child_id` arrive as parameters, passed down the trusted chain
  (user login → accounts issues token → BFF verifies + derives family_id → injects into the agent
  run context → agent calls back here with that family_id).
- Even though the caller is trusted, ownership is STILL enforced in depth: the services scope every
  by-id write through `get_in_family(...)` (CLAUDE.md), so a wrong `family_id`/`child_id` pairing
  404s instead of crossing families. The service token is not a bypass of the family scope.
- RED LINE: this face must never be exposed to the public internet. Bind it to an internal port /
  network only. "No user auth" means service-credentialed, not unauthenticated.

These endpoints use the SAME services as the external face; only the identity source differs (a
`family_id` query param instead of a verified token).
"""

from __future__ import annotations

import hmac
import uuid
from typing import Any

from dishka.integrations.fastapi import DishkaSyncRoute, FromDishka
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from ..config import Settings, get_settings
from ..errors import NotFoundError
from ..schemas import (
    ChildCreate,
    ChildUpdate,
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
    FamilyContextLoader,
    MemberService,
    PolicyService,
)


async def service_guard(
    x_service_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Gate the internal face on a valid `X-Service-Token`.

    Fails closed: if no service token is configured the face is refused entirely (503), never left
    open. A missing/wrong token is 401. Comparison is constant-time.
    """
    expected = settings.service_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="internal face not configured",
        )
    if not x_service_token or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token"
        )


router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    route_class=DishkaSyncRoute,
    dependencies=[Depends(service_guard)],
)


# --- context (read) ---
@router.get("/families/{family_id}/context")
def get_family_context(
    family_id: uuid.UUID, loader: FromDishka[FamilyContextLoader]
) -> dict[str, Any]:
    """Return a family's full per-turn context bundle for the agent's `load_context`.

    Replaces the agent's direct table reads: `{family, members (+profile, age), children
    (+reading_profile, age), policies}`, all scoped to `family_id`. 404 if the family is unknown.
    """
    context = loader.load(family_id)
    if context is None:
        raise NotFoundError
    return context


# --- children ---
@router.post("/children", status_code=status.HTTP_201_CREATED)
def create_child(
    body: ChildCreate,
    svc: FromDishka[ChildService],
    family_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    """Create a child under `family_id` and seed its empty reading profile."""
    return svc.create(family_id, body)


@router.patch("/children/{child_id}")
def update_child(
    child_id: uuid.UUID,
    body: ChildUpdate,
    svc: FromDishka[ChildService],
    family_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    return svc.update(family_id, child_id, body)


@router.put("/children/{child_id}/reading-profile")
def upsert_reading_profile(
    child_id: uuid.UUID,
    body: ReadingProfileUpsert,
    svc: FromDishka[ChildService],
    family_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    return svc.upsert_reading_profile(family_id, child_id, body)


# --- child reading history (a list of books) ---
@router.get("/children/{child_id}/reading-history")
def list_reading_history(
    child_id: uuid.UUID,
    svc: FromDishka[ChildService],
    family_id: uuid.UUID = Query(...),
) -> list[dict[str, Any]]:
    return svc.list_reading_history(family_id, child_id)


@router.post(
    "/children/{child_id}/reading-history", status_code=status.HTTP_201_CREATED
)
def create_reading_history(
    child_id: uuid.UUID,
    body: ReadingHistoryCreate,
    svc: FromDishka[ChildService],
    family_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    return svc.add_reading_history(family_id, child_id, body)


@router.patch("/children/{child_id}/reading-history/{entry_id}")
def update_reading_history(
    child_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: ReadingHistoryUpdate,
    svc: FromDishka[ChildService],
    family_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    return svc.update_reading_history(family_id, child_id, entry_id, body)


# --- members ---
@router.post("/members", status_code=status.HTTP_201_CREATED)
def create_member(
    body: MemberCreate,
    svc: FromDishka[MemberService],
    family_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    return svc.create(family_id, body)


@router.patch("/members/{member_id}")
def update_member(
    member_id: uuid.UUID,
    body: MemberUpdate,
    svc: FromDishka[MemberService],
    family_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    return svc.update(family_id, member_id, body)


@router.put("/members/{member_id}/profile")
def upsert_member_profile(
    member_id: uuid.UUID,
    body: MemberProfileUpsert,
    svc: FromDishka[MemberService],
    family_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    return svc.upsert_profile(family_id, member_id, body)


# --- reading policies ---
@router.post("/policies", status_code=status.HTTP_201_CREATED)
def create_policy(
    body: PolicyCreate,
    svc: FromDishka[PolicyService],
    family_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    return svc.create(family_id, body)


@router.patch("/policies/{policy_id}")
def update_policy(
    policy_id: uuid.UUID,
    body: PolicyUpdate,
    svc: FromDishka[PolicyService],
    family_id: uuid.UUID = Query(...),
) -> dict[str, Any]:
    return svc.update(family_id, policy_id, body)
