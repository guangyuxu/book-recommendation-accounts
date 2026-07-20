"""AuthService — signup / login / refresh / logout (issues access + refresh tokens)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from advanced_alchemy.exceptions import IntegrityError

from ..db.models.family import Family, FamilyMember
from ..db.repositories import FamilyMemberRepository, FamilyRepository
from ..errors import ConflictError, UnauthorizedError
from ..schemas import LoginRequest, SignupRequest
from ..security import PasswordHasher, TokenService
from .invite import InviteService
from .refresh import RefreshTokenService


@dataclass(frozen=True)
class IssuedTokens:
    """The tokens minted on signup / login / refresh.

    `access_token` goes in the JSON body; `refresh_token` (raw) is handed to the router to set as an
    HttpOnly cookie and is NEVER serialized into a response body.
    """

    access_token: str
    family_id: str
    family_member_id: str
    refresh_token: str


class AuthService:
    def __init__(
        self,
        members: FamilyMemberRepository,
        families: FamilyRepository,
        invites: InviteService,
        hasher: PasswordHasher,
        tokens: TokenService,
        refresh: RefreshTokenService,
    ) -> None:
        self._members = members
        self._families = families
        self._invites = invites
        self._hasher = hasher
        self._tokens = tokens
        self._refresh = refresh

    def _issue_tokens(self, family_id: uuid.UUID, member_id: uuid.UUID) -> IssuedTokens:
        """Mint an access token (new lineage) plus a fresh refresh token for a member."""
        family_id_str, member_id_str = str(family_id), str(member_id)
        access = self._tokens.issue(
            family_id=family_id_str, family_member_id=member_id_str
        )
        refresh = self._refresh.issue(family_id=family_id, family_member_id=member_id)
        return IssuedTokens(
            access_token=access,
            family_id=family_id_str,
            family_member_id=member_id_str,
            refresh_token=refresh,
        )

    def signup(self, body: SignupRequest) -> IssuedTokens:
        """Register a user and return an access token + a refresh token.

        With a valid `invite_code`, join that invite's family as a non-primary member; otherwise
        create a new family with this user as its primary member. The joined `family_id` comes from
        the server-side invite row, never from the client.
        """
        if self._members.get_by_email(body.email) is not None:
            raise ConflictError("email already registered")

        if body.invite_code is not None:
            family_id, role = self._invites.redeem(body.invite_code)
            is_primary = False
        else:
            family = self._families.add(
                Family(
                    family_name=body.family_name,
                    default_language=body.language_preference or "en-US",
                )
            )
            family_id, role, is_primary = family.id, body.role, True

        try:
            member = self._members.add(
                FamilyMember(
                    family_id=family_id,
                    display_name=body.display_name,
                    role=role,
                    is_primary_user=is_primary,
                    email=body.email,
                    password_hash=self._hasher.hash(body.password),
                    language_preference=body.language_preference,
                )
            )
        except IntegrityError:  # unique-email race between the check and the insert
            raise ConflictError("email already registered") from None

        return self._issue_tokens(family_id, member.id)

    def login(self, body: LoginRequest) -> IssuedTokens:
        """Verify credentials and return an access token + a refresh token."""
        member = self._members.get_by_email(body.email)
        # Verify even when the member is missing to avoid leaking which emails exist (timing).
        stored = member.password_hash if member else None
        if member is None or not self._hasher.verify(body.password, stored):
            raise UnauthorizedError("invalid credentials")
        return self._issue_tokens(member.family_id, member.id)

    def refresh(self, raw_refresh_token: str) -> IssuedTokens:
        """Rotate a refresh token into a fresh access + refresh token pair.

        Delegates reuse detection to `RefreshTokenService.rotate` (raises 401 on invalid / reused /
        expired), then mints a new access token for the identity the rotated token carried.
        """
        new_refresh, family_id, member_id = self._refresh.rotate(raw_refresh_token)
        access = self._tokens.issue(family_id=family_id, family_member_id=member_id)
        return IssuedTokens(
            access_token=access,
            family_id=family_id,
            family_member_id=member_id,
            refresh_token=new_refresh,
        )

    def logout(self, raw_refresh_token: str) -> None:
        """Revoke the presented refresh token's whole lineage (idempotent)."""
        self._refresh.revoke(raw_refresh_token)
