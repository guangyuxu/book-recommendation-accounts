"""Family-domain repositories (Advanced-Alchemy), mirroring the agent's family repos.

Every by-id read/write goes through `get_in_family(id, family_id)` so a query is NEVER scoped by
id alone — that is the cross-family isolation gate required by CLAUDE.md. This service adds
`get_by_email` to key login.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from advanced_alchemy.repository import SQLAlchemySyncRepository
from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from ..models.family import (
    Family,
    FamilyInvite,
    FamilyMember,
    FamilyMemberProfile,
    FamilyReadingPolicy,
    RefreshToken,
)


class FamilyRepository(SQLAlchemySyncRepository[Family]):
    model_type = Family


class FamilyMemberRepository(SQLAlchemySyncRepository[FamilyMember]):
    model_type = FamilyMember

    def list_by_family(self, family_id: uuid.UUID) -> list[FamilyMember]:
        return self.get_many(
            family_id=family_id, order_by=FamilyMember.created_at.asc()
        )

    def primary_user(self, family_id: uuid.UUID) -> FamilyMember | None:
        return self.get_one_or_none(family_id=family_id, is_primary_user=True)

    def get_by_email(self, email: str) -> FamilyMember | None:
        """Look up a member by (globally unique) login email."""
        return self.get_one_or_none(email=email)

    def get_in_family(
        self, member_id: uuid.UUID, family_id: uuid.UUID
    ) -> FamilyMember | None:
        """Fetch a member ONLY if it belongs to this family (cross-family guard)."""
        return self.get_one_or_none(id=member_id, family_id=family_id)


class FamilyMemberProfileRepository(SQLAlchemySyncRepository[FamilyMemberProfile]):
    model_type = FamilyMemberProfile

    def get_by_member(self, member_id: uuid.UUID) -> FamilyMemberProfile | None:
        return self.get_one_or_none(member_id=member_id)


class FamilyInviteRepository(SQLAlchemySyncRepository[FamilyInvite]):
    model_type = FamilyInvite

    @staticmethod
    def _active_filters() -> list[ColumnElement[bool]]:
        """Unaccepted and not-yet-expired (NULL `expires_at` means no expiry)."""
        now = datetime.now(UTC)
        return [
            FamilyInvite.accepted_at.is_(None),
            or_(FamilyInvite.expires_at.is_(None), FamilyInvite.expires_at > now),
        ]

    def get_active_by_code_hash(self, code_hash: str) -> FamilyInvite | None:
        """Fetch a redeemable invite by its code digest, or None if used/expired/unknown."""
        return self.get_one_or_none(*self._active_filters(), code_hash=code_hash)

    def list_active_for_family(self, family_id: uuid.UUID) -> list[FamilyInvite]:
        return self.get_many(
            *self._active_filters(),
            family_id=family_id,
            order_by=FamilyInvite.created_at.asc(),
        )

    def get_in_family(
        self, invite_id: uuid.UUID, family_id: uuid.UUID
    ) -> FamilyInvite | None:
        """Fetch an invite ONLY if it belongs to this family (cross-family guard)."""
        return self.get_one_or_none(id=invite_id, family_id=family_id)


class FamilyReadingPolicyRepository(SQLAlchemySyncRepository[FamilyReadingPolicy]):
    model_type = FamilyReadingPolicy

    def list_active(
        self, family_id: uuid.UUID, child_id: uuid.UUID | None = None
    ) -> list[FamilyReadingPolicy]:
        filters = [
            FamilyReadingPolicy.family_id == family_id,
            FamilyReadingPolicy.is_active.is_(True),
        ]
        if child_id is not None:
            filters.append(
                or_(
                    FamilyReadingPolicy.child_id == child_id,
                    FamilyReadingPolicy.child_id.is_(None),
                )
            )
        return self.get_many(*filters, order_by=FamilyReadingPolicy.created_at.asc())

    def get_in_family(
        self, policy_id: uuid.UUID, family_id: uuid.UUID
    ) -> FamilyReadingPolicy | None:
        return self.get_one_or_none(id=policy_id, family_id=family_id)


class RefreshTokenRepository(SQLAlchemySyncRepository[RefreshToken]):
    model_type = RefreshToken

    @staticmethod
    def _active_filters() -> list[ColumnElement[bool]]:
        """Not consumed, not revoked, and not-yet-expired (NULL `expires_at` means no expiry)."""
        now = datetime.now(UTC)
        return [
            RefreshToken.consumed_at.is_(None),
            RefreshToken.revoked_at.is_(None),
            or_(RefreshToken.expires_at.is_(None), RefreshToken.expires_at > now),
        ]

    def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        """Fetch a token by digest REGARDLESS of state — callers inspect consumed/revoked/expiry.

        Lookup is by the globally unique digest (like `get_by_email` / `get_active_by_code_hash`):
        the refresh endpoint carries no caller `family_id`; identity is read from the returned row.
        """
        return self.get_one_or_none(token_hash=token_hash)

    def revoke_session(self, session_id: uuid.UUID) -> int:
        """Revoke every still-live token in a rotation lineage; return how many were revoked."""
        now = datetime.now(UTC)
        rows = self.get_many(RefreshToken.revoked_at.is_(None), session_id=session_id)
        for row in rows:
            row.revoked_at = now
            self.update(row)
        return len(rows)

    def revoke_all_for_member(self, member_id: uuid.UUID, family_id: uuid.UUID) -> int:
        """Revoke all of a member's live tokens (e.g. on password change), family-scoped.

        Scoped by BOTH `family_member_id` AND `family_id` so a foreign `family_id` can never touch
        another family's tokens (CLAUDE.md cross-family guard). Returns how many were revoked.
        """
        now = datetime.now(UTC)
        rows = self.get_many(
            RefreshToken.revoked_at.is_(None),
            family_member_id=member_id,
            family_id=family_id,
        )
        for row in rows:
            row.revoked_at = now
            self.update(row)
        return len(rows)
