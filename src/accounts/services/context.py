"""FamilyContextLoader — the per-turn context bundle for the agent (internal read face).

Mirrors the agent's `serialize.load_family_entities` / `lifecycle.load_context` so
`GET /internal/families/{family_id}/context` returns the SAME member / child / policy shapes the
agent used to build by reading the tables directly. `age` is derived from `birth_date` (never
stored); secret columns are dropped by `dump()`. Everything is scoped to `family_id`, so it never
crosses families.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from ..db.models.child import ChildProfile
from ..db.models.family import Family, FamilyMember
from ..db.repositories import (
    ChildProfileRepository,
    FamilyMemberRepository,
    FamilyReadingPolicyRepository,
    FamilyRepository,
)
from ..schemas import dump


def _age(dob: date | None) -> int | None:
    """Whole years from a date of birth to today, or None if unknown."""
    if dob is None:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class FamilyContextLoader:
    def __init__(
        self,
        families: FamilyRepository,
        members: FamilyMemberRepository,
        children: ChildProfileRepository,
        policies: FamilyReadingPolicyRepository,
    ) -> None:
        self._families = families
        self._members = members
        self._children = children
        self._policies = policies

    def load(self, family_id: uuid.UUID) -> dict[str, Any] | None:
        """Return the full context bundle for a family, or None if the family is absent.

        Shape (matches the agent's `load_context`):
            {"family": {...}, "members": [...], "children": {"<id>": {...}}, "policies": [...]}
        """
        family: Family | None = self._families.get_one_or_none(id=family_id)
        if family is None:
            return None

        members = [
            self._serialize_member(m) for m in self._members.list_by_family(family_id)
        ]
        children = {
            str(c.id): self._serialize_child(c)
            for c in self._children.list_by_family(family_id)
        }
        policies = [dump(p) for p in self._policies.list_active(family_id)]
        return {
            "family": dump(family),
            "members": members,
            "children": children,
            "policies": policies,
        }

    def _serialize_member(self, member: FamilyMember) -> dict[str, Any]:
        """One member row -> context dict, with its 1:1 profile and derived age."""
        data = dump(member)
        data["profile"] = dump(member.profile) if member.profile else {}
        data["age"] = _age(member.birth_date)
        return data

    def _serialize_child(self, child: ChildProfile) -> dict[str, Any]:
        """One child row -> context dict, with its 1:1 reading_profile and derived age."""
        data = dump(child)
        data["reading_profile"] = (
            dump(child.reading_profile) if child.reading_profile else {}
        )
        data["age"] = _age(child.birth_date)
        return data
