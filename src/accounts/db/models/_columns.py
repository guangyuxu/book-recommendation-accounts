"""Shared column helpers for the `accounts` schema.

These reproduce the live column shapes: server-generated UUID PKs (`gen_random_uuid()`),
`now()`-defaulted timezone-aware timestamps, and a non-native `Gender` enum stored as VARCHAR(16)
+ CHECK (validated at the edge by a Pydantic Literal too). Age is never stored — it is derived
from `birth_date` at read time.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column


class Gender(StrEnum):
    """Stored as VARCHAR(16) with a CHECK constraint (native_enum=False)."""

    MALE = "Male"
    FEMALE = "Female"


def _gender() -> Mapped[Gender | None]:
    return mapped_column(
        Enum(
            Gender,
            native_enum=False,
            length=16,
            values_callable=lambda enum: [m.value for m in enum],
        )
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
