"""Signup / login / refresh / logout / identity endpoints (external face).

Thin adapters over `AuthService` (which creates the family + primary member on signup, redeems
invites, and issues access + refresh tokens) and the injected `Identity` (re-derived server-side
from the verified token on every request).

Token handling: the access token is returned in the JSON body; the refresh token is set as an
**HttpOnly + Secure + SameSite** cookie scoped to `/auth`, so it is only ever sent back to the
refresh/logout endpoints and is never readable by frontend JS. `password_hash` is never returned.
"""

from __future__ import annotations

import uuid

from dishka.integrations.fastapi import DishkaSyncRoute, FromDishka
from fastapi import APIRouter, Cookie, Depends, Response, status

from ..auth import Identity, bearer_scheme
from ..config import Settings
from ..errors import NotFoundError, UnauthorizedError
from ..schemas import LoginRequest, SignupRequest, TokenResponse
from ..services import AuthService, IssuedTokens, MemberService

router = APIRouter(tags=["auth"], route_class=DishkaSyncRoute)


def _set_refresh_cookie(response: Response, settings: Settings, raw: str) -> None:
    """Set the refresh-token cookie (HttpOnly, /auth-scoped) from the configured policy."""
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw,
        max_age=settings.refresh_ttl_seconds,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path=settings.refresh_cookie_path,
    )


def _token_body(tokens: IssuedTokens) -> TokenResponse:
    """Map issued tokens to the JSON body (the raw refresh token is NEVER included here)."""
    return TokenResponse(
        access_token=tokens.access_token,
        family_id=tokens.family_id,
        family_member_id=tokens.family_member_id,
    )


@router.post(
    "/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
def signup(
    body: SignupRequest,
    response: Response,
    svc: FromDishka[AuthService],
    settings: FromDishka[Settings],
) -> TokenResponse:
    """Register a user; return an access token and set the refresh-token cookie.

    With a valid `invite_code`, join that invite's family as a non-primary member; otherwise create
    a new family with this user as its primary member. The joined `family_id` is taken from the
    server-side invite row, never from the client.
    """
    tokens = svc.signup(body)
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return _token_body(tokens)


@router.post("/auth/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    svc: FromDishka[AuthService],
    settings: FromDishka[Settings],
) -> TokenResponse:
    """Verify credentials; return an access token and set the refresh-token cookie."""
    tokens = svc.login(body)
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return _token_body(tokens)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    svc: FromDishka[AuthService],
    settings: FromDishka[Settings],
    refresh_token: str | None = Cookie(default=None),
) -> TokenResponse:
    """Rotate the refresh-token cookie into a fresh access token + new refresh cookie.

    The refresh token arrives via the HttpOnly cookie (never the body). Rotation is one-time-use;
    presenting a reused/revoked/expired token fails with 401 (see `RefreshTokenService.rotate`).
    """
    if not refresh_token:
        raise UnauthorizedError("missing refresh token")
    tokens = svc.refresh(refresh_token)
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return _token_body(tokens)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    svc: FromDishka[AuthService],
    settings: FromDishka[Settings],
    refresh_token: str | None = Cookie(default=None),
) -> None:
    """Revoke the refresh token's whole lineage and clear the cookie (idempotent)."""
    if refresh_token:
        svc.logout(refresh_token)
    response.delete_cookie(
        key=settings.refresh_cookie_name, path=settings.refresh_cookie_path
    )


@router.get("/me", dependencies=[Depends(bearer_scheme)])
def me(
    identity: FromDishka[Identity], svc: FromDishka[MemberService]
) -> dict[str, str | None]:
    """Return the caller's own identity, plus `email`/`display_name` when a member row is resolvable.

    Replaces a separate id token: the frontend reads the authenticated user's own identity here.
    `email`/`display_name` are the caller's OWN data, read via the family-scoped `get(...)`. Falls
    back to identity-only when the id is not a resolvable member row (e.g. a token for a member that
    was since deleted), so `/me` still returns the verified identity.
    """
    context = identity.to_context()
    try:
        member = svc.get(
            uuid.UUID(identity.family_id), uuid.UUID(identity.family_member_id)
        )
    except (ValueError, NotFoundError):
        return context
    return {
        **context,
        "email": member.get("email"),
        "display_name": member.get("display_name"),
    }
