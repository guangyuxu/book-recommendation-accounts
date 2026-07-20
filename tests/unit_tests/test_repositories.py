"""Repository-level cross-family isolation (CLAUDE.md) and email uniqueness."""

from __future__ import annotations

import pytest
from advanced_alchemy.exceptions import DuplicateKeyError

from accounts.db import session_scope
from accounts.db.models.child import ChildProfile
from accounts.db.models.family import Family, FamilyMember
from accounts.db.repositories import (
    ChildProfileRepository,
    FamilyMemberRepository,
)


def FamilyRepo_add(session: object, fam: Family) -> Family:
    from accounts.db.repositories import FamilyRepository

    return FamilyRepository(session=session).add(fam)


def test_child_get_in_family_is_cross_family_scoped() -> None:
    # Seed a child under family A, then try to read it as family B.
    with session_scope() as session:
        fam_a = FamilyRepo_add(session, Family(family_name="A")).id
        fam_b = FamilyRepo_add(session, Family(family_name="B")).id
        child = ChildProfileRepository(session=session).add(
            ChildProfile(family_id=fam_a, display_name="Kid")
        )
        child_id = child.id

    with session_scope() as session:
        repo = ChildProfileRepository(session=session)
        assert repo.get_in_family(child_id, fam_a) is not None
        # Family B must NOT be able to reach family A's child.
        assert repo.get_in_family(child_id, fam_b) is None
        assert repo.list_by_family(fam_b) == []


def test_member_get_in_family_is_cross_family_scoped() -> None:
    with session_scope() as session:
        fam_a = FamilyRepo_add(session, Family(family_name="A")).id
        fam_b = FamilyRepo_add(session, Family(family_name="B")).id
        member = FamilyMemberRepository(session=session).add(
            FamilyMember(family_id=fam_a, role="parent")
        )
        member_id = member.id

    with session_scope() as session:
        repo = FamilyMemberRepository(session=session)
        assert repo.get_in_family(member_id, fam_a) is not None
        assert repo.get_in_family(member_id, fam_b) is None


def test_email_is_unique() -> None:
    with session_scope() as session:
        fam = FamilyRepo_add(session, Family(family_name="A")).id
        FamilyMemberRepository(session=session).add(
            FamilyMember(family_id=fam, role="parent", email="dup@example.com")
        )
    with pytest.raises(DuplicateKeyError):
        with session_scope() as session:
            fam2 = FamilyRepo_add(session, Family(family_name="B")).id
            FamilyMemberRepository(session=session).add(
                FamilyMember(family_id=fam2, role="parent", email="dup@example.com")
            )
