"""Family-scoped repositories over the shared schema.

Build one per request on a `session_scope()` session (keyword-only `session=`), e.g.
`FamilyMemberRepository(session=s)`. Cross-family reads/writes always go through
`get_in_family(...)` / an explicit `family_id` filter.
"""

from .child import (
    ChildProfileRepository,
    ChildReadingProfileRepository,
    ReadingHistoryRepository,
)
from .family import (
    FamilyInviteRepository,
    FamilyMemberProfileRepository,
    FamilyMemberRepository,
    FamilyReadingPolicyRepository,
    FamilyRepository,
    RefreshTokenRepository,
)

__all__ = [
    "FamilyRepository",
    "FamilyMemberRepository",
    "FamilyMemberProfileRepository",
    "FamilyReadingPolicyRepository",
    "FamilyInviteRepository",
    "RefreshTokenRepository",
    "ChildProfileRepository",
    "ChildReadingProfileRepository",
    "ReadingHistoryRepository",
]
