"""InviteService — second-member join flow (create / list / revoke / redeem)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ..db.models.family import FamilyInvite
from ..db.repositories import FamilyInviteRepository
from ..errors import BadRequestError, NotFoundError
from ..schemas import InviteCreate, InviteResponse, dump
from ..security import InviteCodec


class InviteService:
    def __init__(self, invites: FamilyInviteRepository, codec: InviteCodec) -> None:
        self._invites = invites
        self._codec = codec

    def create(
        self,
        family_id: uuid.UUID,
        created_by_member_id: uuid.UUID,
        body: InviteCreate,
    ) -> InviteResponse:
        """Create a single-use invite; the raw code is returned only here (never stored raw)."""
        code = self._codec.generate()
        expires_at = (
            datetime.now(UTC) + timedelta(hours=body.ttl_hours)
            if body.ttl_hours is not None
            else None
        )
        invite = self._invites.add(
            FamilyInvite(
                family_id=family_id,
                code_hash=self._codec.hash(code),
                role=body.role,
                created_by_member_id=created_by_member_id,
                expires_at=expires_at,
            )
        )
        return InviteResponse(
            id=str(invite.id),
            code=code,
            role=invite.role,
            family_id=str(family_id),
            expires_at=invite.expires_at,
        )

    def list(self, family_id: uuid.UUID) -> list[dict[str, Any]]:
        """List the family's active (unredeemed, unexpired) invites; codes are never returned."""
        return [dump(i) for i in self._invites.list_active_for_family(family_id)]

    def revoke(self, family_id: uuid.UUID, invite_id: uuid.UUID) -> None:
        invite = self._invites.get_in_family(invite_id, family_id)
        if invite is None:
            raise NotFoundError
        self._invites.delete(invite.id)

    def redeem(self, code: str) -> tuple[uuid.UUID, str]:
        """Redeem an invite code: return (family_id, role) and mark it accepted (single-use).

        The family is bound by the invite, so a joining client can never choose which family to
        enter. Raises `BadRequestError` if the code is unknown / used / expired.
        """
        invite = self._invites.get_active_by_code_hash(self._codec.hash(code))
        if invite is None:
            raise BadRequestError("invalid or expired invite code")
        invite.accepted_at = datetime.now(UTC)
        self._invites.update(invite)
        return invite.family_id, invite.role
