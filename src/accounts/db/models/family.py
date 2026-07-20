"""Family-domain ORM models for the `accounts` schema.

Columns map the live `accounts` tables. Authentication on `FamilyMember` (`email` +
`password_hash`) is owned by this service — the IdP — which keys login on the (unique) `email`;
both are nullable so pre-existing members without a login stay valid. `FamilyInvite` backs the
invite-code join flow: a second person signs up with a code and joins an existing family.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, JSONType, TextArray
from ._columns import Gender, _created_at, _gender, _updated_at, _uuid_pk

if TYPE_CHECKING:
    from .child import ChildProfile


class Family(Base):
    __tablename__ = "family"

    id: Mapped[uuid.UUID] = _uuid_pk()
    family_name: Mapped[str | None] = mapped_column(Text)
    default_language: Mapped[str | None] = mapped_column(
        Text, server_default=text("'en-US'")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    members: Mapped[list[FamilyMember]] = relationship(
        back_populates="family",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    children: Mapped[list[ChildProfile]] = relationship(
        back_populates="family",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    policies: Mapped[list[FamilyReadingPolicy]] = relationship(
        back_populates="family",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class FamilyMember(Base):
    __tablename__ = "family_member"
    __table_args__ = (Index("idx_family_member_family_id", "family_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family.id"), nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(Text)
    gender: Mapped[Gender | None] = _gender()
    birth_date: Mapped[date | None] = mapped_column(Date)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary_user: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    language_preference: Mapped[str | None] = mapped_column(
        Text, server_default=text("'zh-CN'")
    )
    # --- auth columns owned by this service (not present in the agent's schema) ---
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    family: Mapped[Family] = relationship(back_populates="members", lazy="selectin")
    profile: Mapped[FamilyMemberProfile | None] = relationship(
        back_populates="member",
        lazy="selectin",
        uselist=False,
        cascade="all, delete-orphan",
    )


class FamilyMemberProfile(Base):
    __tablename__ = "family_member_profile"

    id: Mapped[uuid.UUID] = _uuid_pk()
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_member.id"), nullable=False, unique=True
    )
    occupation_background: Mapped[str | None] = mapped_column(Text)
    education_background: Mapped[str | None] = mapped_column(Text)
    communication_style: Mapped[str | None] = mapped_column(Text)
    concerns: Mapped[list[str]] = mapped_column(TextArray, server_default=text("'{}'"))
    source: Mapped[str | None] = mapped_column(
        Text, server_default=text("'parent_report'")
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    member: Mapped[FamilyMember] = relationship(
        back_populates="profile", lazy="selectin"
    )


class FamilyReadingPolicy(Base):
    __tablename__ = "family_reading_policy"
    __table_args__ = (
        Index("idx_family_reading_policy_family_id", "family_id"),
        Index("idx_family_reading_policy_child_id", "child_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family.id"), nullable=False
    )
    child_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("child_profile.id"))
    goals: Mapped[list[str]] = mapped_column(TextArray, server_default=text("'{}'"))
    constraints: Mapped[list[str]] = mapped_column(
        TextArray, server_default=text("'{}'")
    )
    avoid_topics: Mapped[list[str]] = mapped_column(
        TextArray, server_default=text("'{}'")
    )
    content_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONType, server_default=text("'{}'")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    family: Mapped[Family] = relationship(back_populates="policies", lazy="selectin")
    child: Mapped[ChildProfile | None] = relationship(lazy="selectin")


class FamilyInvite(Base):
    """A single-use invite that lets a second person sign up INTO an existing family.

    The raw code is never stored — only its SHA-256 digest (`code_hash`). `family_id` is bound to
    the invite server-side, so a joining client cannot influence which family they land in.
    """

    __tablename__ = "family_invite"
    __table_args__ = (Index("idx_family_invite_family_id", "family_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family.id"), nullable=False
    )
    # SHA-256 hex digest of the raw invite code (unique so a presented code maps to one invite).
    code_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'member'")
    )
    created_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("family_member.id")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # NULL until redeemed; set once, enforcing single use.
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    family: Mapped[Family] = relationship(lazy="selectin")


class RefreshToken(Base):
    """A refresh token issued at login/signup, exchanged for new access tokens (rotation).

    Only the SHA-256 digest of the raw token is stored (`token_hash`, unique) — the raw value is
    returned once, into an HttpOnly cookie, and never persisted. Rotation is one-time-use: each
    exchange sets `consumed_at` and issues a NEW row sharing the same `session_id` (the rotation
    lineage). Presenting a token that is already `consumed_at`/`revoked_at` is treated as reuse and
    revokes the whole `session_id`. `family_id` is stored so revocation can be family-scoped.
    """

    __tablename__ = "refresh_token"
    __table_args__ = (
        Index("idx_refresh_token_family_member_id", "family_member_id"),
        Index("idx_refresh_token_session_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family.id"), nullable=False
    )
    family_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_member.id"), nullable=False
    )
    # Rotation lineage: all tokens minted from one login share this id (revoked together on reuse).
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # SHA-256 hex digest of the raw refresh token (unique so a presented token maps to one row).
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Absolute expiry (30d cap by default); NULL is never written.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set once when rotated (one-time use); a second presentation is reuse.
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set on logout / reuse detection / password change.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
