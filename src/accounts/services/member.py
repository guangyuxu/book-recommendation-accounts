"""MemberService — family members and their 1:1 profile (shared by both faces).

`create` handles the external face (optional login `email`/`password` → hashed + uniqueness check)
and the internal face (agent-created members carry no credentials) with one code path: the optional
fields are simply absent for internal callers.
"""

from __future__ import annotations

import uuid
from typing import Any

from advanced_alchemy.exceptions import IntegrityError

from ..db.models.family import FamilyMember, FamilyMemberProfile
from ..db.repositories import FamilyMemberProfileRepository, FamilyMemberRepository
from ..errors import ConflictError, NotFoundError
from ..schemas import MemberCreate, MemberProfileUpsert, MemberUpdate, dump
from ..security import PasswordHasher
from ._util import apply_changes


class MemberService:
    def __init__(
        self,
        members: FamilyMemberRepository,
        profiles: FamilyMemberProfileRepository,
        hasher: PasswordHasher,
    ) -> None:
        self._members = members
        self._profiles = profiles
        self._hasher = hasher

    def list(self, family_id: uuid.UUID) -> list[dict[str, Any]]:
        return [dump(m) for m in self._members.list_by_family(family_id)]

    def create(self, family_id: uuid.UUID, body: MemberCreate) -> dict[str, Any]:
        if (
            body.email is not None
            and self._members.get_by_email(body.email) is not None
        ):
            raise ConflictError("email already registered")
        try:
            member = self._members.add(
                FamilyMember(
                    family_id=family_id,
                    display_name=body.display_name,
                    role=body.role,
                    gender=body.gender,
                    birth_date=body.birth_date,
                    language_preference=body.language_preference,
                    email=body.email,
                    password_hash=self._hasher.hash(body.password)
                    if body.password
                    else None,
                )
            )
        except IntegrityError:  # unique-email race
            raise ConflictError("email already registered") from None
        return dump(member)

    def get(self, family_id: uuid.UUID, member_id: uuid.UUID) -> dict[str, Any]:
        member = self._members.get_in_family(member_id, family_id)
        if member is None:
            raise NotFoundError
        return dump(member)

    def update(
        self, family_id: uuid.UUID, member_id: uuid.UUID, body: MemberUpdate
    ) -> dict[str, Any]:
        member = self._members.get_in_family(member_id, family_id)
        if member is None:
            raise NotFoundError
        apply_changes(member, body.model_dump(exclude_unset=True))
        return dump(self._members.update(member))

    def delete(self, family_id: uuid.UUID, member_id: uuid.UUID) -> None:
        member = self._members.get_in_family(member_id, family_id)
        if member is None:
            raise NotFoundError
        if member.is_primary_user:
            raise ConflictError("cannot delete the primary member")
        self._members.delete(member.id)

    def get_profile(self, family_id: uuid.UUID, member_id: uuid.UUID) -> dict[str, Any]:
        # Ownership: the member must belong to this family before reading its 1:1 profile.
        member = self._members.get_in_family(member_id, family_id)
        if member is None:
            raise NotFoundError
        profile = self._profiles.get_by_member(member_id)
        if profile is None:
            raise NotFoundError
        return dump(profile)

    def upsert_profile(
        self, family_id: uuid.UUID, member_id: uuid.UUID, body: MemberProfileUpsert
    ) -> dict[str, Any]:
        # Ownership: the member must belong to this family before touching its 1:1 profile.
        member = self._members.get_in_family(member_id, family_id)
        if member is None:
            raise NotFoundError
        profile = self._profiles.get_by_member(member_id)
        changes = body.model_dump(exclude_unset=True)
        if profile is None:
            profile = self._profiles.add(
                FamilyMemberProfile(member_id=member_id, **changes)
            )
        else:
            apply_changes(profile, changes)
            profile = self._profiles.update(profile)
        return dump(profile)
