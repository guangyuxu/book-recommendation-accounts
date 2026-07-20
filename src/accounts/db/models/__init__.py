"""ORM models for the accounts service — the account/profile tables under the `accounts` schema.

These map the live `accounts` tables this service owns. The models are the single source of truth
for the schema. Importing this package registers every model on `Base.metadata`, so `init_db()`
(`CREATE SCHEMA IF NOT EXISTS` + `create_all`) and the sqlite used by tests all see them.

Scope: family / member (+ profile) / child (+ reading profile) / reading policy / family invite —
signup, the invite-based join flow, and family management. `reading_history` is modeled for schema
fidelity + FK integrity only (no CRUD endpoints).
"""

from .child import ChildProfile, ChildReadingProfile, ReadingHistory
from .family import (
    Family,
    FamilyInvite,
    FamilyMember,
    FamilyMemberProfile,
    FamilyReadingPolicy,
    RefreshToken,
)

__all__ = [
    "Family",
    "FamilyMember",
    "FamilyMemberProfile",
    "FamilyReadingPolicy",
    "FamilyInvite",
    "RefreshToken",
    "ChildProfile",
    "ChildReadingProfile",
    "ReadingHistory",
]
