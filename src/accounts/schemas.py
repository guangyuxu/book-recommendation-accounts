"""Pydantic request/response models and a PII-aware serializer for ORM rows.

Request models validate and constrain client input at the edge. Responses are built by `dump()`,
which serializes an ORM row via Advanced-Alchemy's `to_dict()` and JSON-encodes it — after dropping
secret columns (never expose `password_hash`).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, cast

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, field_validator

GenderLiteral = Literal["Male", "Female"]

# Columns that must never appear in an API response (password + invite-code / refresh-token digest).
_SECRET_COLUMNS = frozenset({"password_hash", "code_hash", "token_hash"})


def dump(model: Any, *, extra_exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Serialize an ORM row to a JSON-safe dict, dropping secret columns."""
    data: dict[str, Any] = dict(model.to_dict())
    for key in _SECRET_COLUMNS | extra_exclude:
        data.pop(key, None)
    return cast(dict[str, Any], jsonable_encoder(data))


# --- auth ---
class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=256)
    family_name: str | None = None
    display_name: str | None = None
    role: str = "parent"
    language_preference: str | None = None
    # When set, join the invite's family (as a non-primary member) instead of creating a new one.
    invite_code: str | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("invalid email address")
        return v


class InviteCreate(BaseModel):
    """Create an invite for the caller's family. Defaults: role `member`, single-use, 72h TTL."""

    role: str = "member"
    # Hours until the code expires; None means it never expires.
    ttl_hours: int | None = Field(default=72, gt=0)


class InviteResponse(BaseModel):
    """Returned once on creation — the raw `code` is never retrievable again."""

    id: str
    code: str
    role: str
    family_id: str
    expires_at: datetime | None


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 — OAuth token_type label, not a secret
    family_id: str
    family_member_id: str


# --- family ---
class FamilyUpdate(BaseModel):
    family_name: str | None = None
    default_language: str | None = None


# --- members ---
class MemberCreate(BaseModel):
    display_name: str | None = None
    role: str = "member"
    gender: GenderLiteral | None = None
    birth_date: date | None = None
    language_preference: str | None = None
    # Optional login credentials — set to let this member sign in too.
    email: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else v


class MemberUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    gender: GenderLiteral | None = None
    birth_date: date | None = None
    language_preference: str | None = None


class MemberProfileUpsert(BaseModel):
    """The 1:1 `family_member_profile` row (agent-curated parent context)."""

    occupation_background: str | None = None
    education_background: str | None = None
    communication_style: str | None = None
    concerns: list[str] | None = None
    source: str | None = None
    confidence: float | None = None


# --- children ---
class ChildCreate(BaseModel):
    display_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    gender: GenderLiteral | None = None
    birth_date: date | None = None
    grade: str | None = None
    school_system: str | None = None
    country_or_curriculum: str | None = None
    primary_language: str | None = None
    reading_language: str | None = None
    notes: str | None = None


class ChildUpdate(BaseModel):
    display_name: str | None = None
    aliases: list[str] | None = None
    gender: GenderLiteral | None = None
    birth_date: date | None = None
    grade: str | None = None
    school_system: str | None = None
    country_or_curriculum: str | None = None
    primary_language: str | None = None
    reading_language: str | None = None
    notes: str | None = None


class ReadingProfileUpsert(BaseModel):
    reading_level_note: str | None = None
    cefr_level: str | None = None
    lexile: int | None = None
    ar_level: float | None = None
    current_stage: str | None = None
    independent_reading: bool | None = None
    needs_dictionary: bool | None = None
    can_read_chapter_books: bool | None = None
    can_handle_old_language: bool | None = None
    interests: list[str] | None = None
    preferred_genres: list[str] | None = None
    disliked_genres: list[str] | None = None
    liked_themes: list[str] | None = None
    disliked_themes: list[str] | None = None
    preferred_tone: list[str] | None = None
    avoid_topics: list[str] | None = None
    summary: str | None = None


# --- reading history (a child's read/reading books; a list, not a 1:1 row) ---
class ReadingHistoryCreate(BaseModel):
    title: str | None = None
    author: str | None = None
    series_name: str | None = None
    book_order: str | None = None
    status: str | None = None
    liked: bool | None = None
    reasons: list[str] = Field(default_factory=list)
    parent_note: str | None = None
    child_note: str | None = None
    started_at: date | None = None
    finished_at: date | None = None


class ReadingHistoryUpdate(BaseModel):
    title: str | None = None
    author: str | None = None
    series_name: str | None = None
    book_order: str | None = None
    status: str | None = None
    liked: bool | None = None
    reasons: list[str] | None = None
    parent_note: str | None = None
    child_note: str | None = None
    started_at: date | None = None
    finished_at: date | None = None


# --- reading policy ---
class PolicyCreate(BaseModel):
    child_id: str | None = None
    goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    avoid_topics: list[str] = Field(default_factory=list)
    content_preferences: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    is_active: bool = True


class PolicyUpdate(BaseModel):
    goals: list[str] | None = None
    constraints: list[str] | None = None
    avoid_topics: list[str] | None = None
    content_preferences: dict[str, Any] | None = None
    notes: str | None = None
    is_active: bool | None = None
