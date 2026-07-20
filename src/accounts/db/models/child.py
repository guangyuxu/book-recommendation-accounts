"""Child-domain ORM models for the `accounts` schema.

`ChildProfile` is the request's `child_id`; `ChildReadingProfile` is the 1:1 curated reading
profile. `ReadingHistory` maps the live `reading_history` table for schema fidelity and FK
integrity only — this service exposes no CRUD endpoints for it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TextArray
from ._columns import Gender, _created_at, _gender, _updated_at, _uuid_pk
from .family import Family


class ChildProfile(Base):
    __tablename__ = "child_profile"
    __table_args__ = (Index("idx_child_profile_family_id", "family_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family.id"), nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(TextArray, server_default=text("'{}'"))
    gender: Mapped[Gender | None] = _gender()
    birth_date: Mapped[date | None] = mapped_column(Date)
    grade: Mapped[str | None] = mapped_column(Text)
    school_system: Mapped[str | None] = mapped_column(Text)
    country_or_curriculum: Mapped[str | None] = mapped_column(Text)
    primary_language: Mapped[str | None] = mapped_column(Text)
    reading_language: Mapped[str | None] = mapped_column(
        Text, server_default=text("'English'")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    family: Mapped[Family] = relationship(back_populates="children", lazy="selectin")
    reading_profile: Mapped[ChildReadingProfile | None] = relationship(
        back_populates="child",
        lazy="selectin",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ChildReadingProfile(Base):
    __tablename__ = "child_reading_profile"

    id: Mapped[uuid.UUID] = _uuid_pk()
    child_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("child_profile.id"), nullable=False, unique=True
    )
    reading_level_note: Mapped[str | None] = mapped_column(Text)
    cefr_level: Mapped[str | None] = mapped_column(Text)
    lexile: Mapped[int | None] = mapped_column(Integer)
    ar_level: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    current_stage: Mapped[str | None] = mapped_column(Text)
    independent_reading: Mapped[bool | None] = mapped_column()
    needs_dictionary: Mapped[bool | None] = mapped_column()
    can_read_chapter_books: Mapped[bool | None] = mapped_column()
    can_handle_old_language: Mapped[bool | None] = mapped_column()
    interests: Mapped[list[str]] = mapped_column(TextArray, server_default=text("'{}'"))
    preferred_genres: Mapped[list[str]] = mapped_column(
        TextArray, server_default=text("'{}'")
    )
    disliked_genres: Mapped[list[str]] = mapped_column(
        TextArray, server_default=text("'{}'")
    )
    liked_themes: Mapped[list[str]] = mapped_column(
        TextArray, server_default=text("'{}'")
    )
    disliked_themes: Mapped[list[str]] = mapped_column(
        TextArray, server_default=text("'{}'")
    )
    preferred_tone: Mapped[list[str]] = mapped_column(
        TextArray, server_default=text("'{}'")
    )
    avoid_topics: Mapped[list[str]] = mapped_column(
        TextArray, server_default=text("'{}'")
    )
    summary: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    source: Mapped[str | None] = mapped_column(
        Text, server_default=text("'parent_report'")
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    child: Mapped[ChildProfile] = relationship(
        back_populates="reading_profile", lazy="selectin"
    )


class ReadingHistory(Base):
    """Live `reading_history` table — modeled for schema fidelity + FK integrity, no endpoints."""

    __tablename__ = "reading_history"
    __table_args__ = (Index("idx_reading_history_child_id", "child_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    child_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("child_profile.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    series_name: Mapped[str | None] = mapped_column(Text)
    book_order: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    liked: Mapped[bool | None] = mapped_column(Boolean)
    reasons: Mapped[list[str]] = mapped_column(TextArray, server_default=text("'{}'"))
    parent_note: Mapped[str | None] = mapped_column(Text)
    child_note: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[date | None] = mapped_column(Date)
    finished_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
