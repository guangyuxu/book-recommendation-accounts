"""Caller-identity resolution for the accounts service's OWN endpoints (external face).

The accounts service issues tokens AND verifies its own tokens to protect its CRUD endpoints. The
seam mirrors the BFF's so local and production share ONE code path: an `IdentityResolver` takes the
request and returns an `Identity`.

`BearerIdentityResolver` verifies the `Bearer <jwt>` (RS256, own public key via `TokenService`) and
derives `family_id` / `family_member_id` from the verified claims.

Identity is ALWAYS derived server-side here; it is never read from client-supplied body/query
params. This is the authorization gate for the external CRUD face (see CLAUDE.md). The INTERNAL
face (`/internal/*`, for the agent) uses a separate service-token guard (see routers/internal.py).

The resolvers are framework-free collaborators wired in `accounts.providers`, which also provides
the REQUEST-scoped `Identity` (built from the incoming `Request` + the configured resolver); routers
consume that injected `Identity` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import jwt
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer

from .security import TokenService

# Documentation-only security scheme (approach 3: co-located with the resolver, but decoupled from
# enforcement). It exists ONLY to describe the external face's contract in OpenAPI — so Swagger
# renders the "Authorize" button and attaches `Authorization: Bearer <token>`. It never verifies or
# rejects: `auto_error=False` keeps missing/invalid tokens flowing to `BearerIdentityResolver`,
# which remains the single enforcement path (and the 401 envelope). Kept here, next to the resolver,
# so the "external contract" (describe + enforce) lives in one module and the two cannot silently
# drift. Attach via `dependencies=[Depends(bearer_scheme)]`; its return value is intentionally unused.
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    """The resolved caller identity."""

    family_id: str
    family_member_id: str
    child_id: str | None = None

    def to_context(self) -> dict[str, str | None]:
        return {
            "family_id": self.family_id,
            "family_member_id": self.family_member_id,
            "child_id": self.child_id,
        }


class IdentityResolver(Protocol):
    """Resolves the caller identity from the incoming request."""

    def resolve(self, request: Request) -> Identity: ...


class BearerIdentityResolver:
    """Verifies the `Bearer <jwt>` header (RS256) and derives identity from the token's claims.

    `family_id` / `family_member_id` come ONLY from the verified token — never from the client's
    body or query — so this remains the authorization gate (see CLAUDE.md). Fails closed with 401.
    """

    def __init__(self, tokens: TokenService) -> None:
        self._tokens = tokens

    def resolve(self, request: Request) -> Identity:
        authorization = request.headers.get("authorization")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing or malformed Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            claims = self._tokens.decode(token)
            return Identity(
                family_id=str(claims["family_id"]),
                family_member_id=str(claims["family_member_id"]),
            )
        except (jwt.InvalidTokenError, KeyError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
