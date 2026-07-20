"""ChildService — child profiles and their 1:1 reading profile (shared by both faces)."""

from __future__ import annotations

import builtins
import uuid
from typing import Any

from ..db.models.child import ChildProfile, ChildReadingProfile, ReadingHistory
from ..db.repositories import (
    ChildProfileRepository,
    ChildReadingProfileRepository,
    ReadingHistoryRepository,
)
from ..errors import NotFoundError
from ..schemas import (
    ChildCreate,
    ChildUpdate,
    ReadingHistoryCreate,
    ReadingHistoryUpdate,
    ReadingProfileUpsert,
    dump,
)
from ._util import apply_changes


class ChildService:
    def __init__(
        self,
        children: ChildProfileRepository,
        reading: ChildReadingProfileRepository,
        history: ReadingHistoryRepository,
    ) -> None:
        self._children = children
        self._reading = reading
        self._history = history

    def list(self, family_id: uuid.UUID) -> list[dict[str, Any]]:
        return [dump(c) for c in self._children.list_by_family(family_id)]

    def create(self, family_id: uuid.UUID, body: ChildCreate) -> dict[str, Any]:
        """Create a child under `family_id` and seed its empty reading profile."""
        child = self._children.add(
            ChildProfile(family_id=family_id, **body.model_dump())
        )
        self._reading.add(ChildReadingProfile(child_id=child.id))
        return dump(child)

    def get(self, family_id: uuid.UUID, child_id: uuid.UUID) -> dict[str, Any]:
        child = self._children.get_in_family(child_id, family_id)
        if child is None:
            raise NotFoundError
        return dump(child)

    def update(
        self, family_id: uuid.UUID, child_id: uuid.UUID, body: ChildUpdate
    ) -> dict[str, Any]:
        child = self._children.get_in_family(child_id, family_id)
        if child is None:
            raise NotFoundError
        apply_changes(child, body.model_dump(exclude_unset=True))
        return dump(self._children.update(child))

    def delete(self, family_id: uuid.UUID, child_id: uuid.UUID) -> None:
        child = self._children.get_in_family(child_id, family_id)
        if child is None:
            raise NotFoundError
        self._children.delete(child.id)

    def get_reading_profile(
        self, family_id: uuid.UUID, child_id: uuid.UUID
    ) -> dict[str, Any]:
        child = self._children.get_in_family(child_id, family_id)
        if child is None:
            raise NotFoundError
        profile = self._reading.get_by_child(child_id)
        if profile is None:
            raise NotFoundError
        return dump(profile)

    def upsert_reading_profile(
        self, family_id: uuid.UUID, child_id: uuid.UUID, body: ReadingProfileUpsert
    ) -> dict[str, Any]:
        child = self._children.get_in_family(child_id, family_id)
        if child is None:
            raise NotFoundError
        profile = self._reading.get_by_child(child_id)
        changes = body.model_dump(exclude_unset=True)
        if profile is None:
            profile = self._reading.add(
                ChildReadingProfile(child_id=child_id, **changes)
            )
        else:
            apply_changes(profile, changes)
            profile = self._reading.update(profile)
        return dump(profile)

    # --- reading history (a list of books per child) ---
    def _require_child(self, family_id: uuid.UUID, child_id: uuid.UUID) -> None:
        # Cross-family guard: every reading-history op is scoped to a child in the caller's family.
        if self._children.get_in_family(child_id, family_id) is None:
            raise NotFoundError

    def list_reading_history(
        self, family_id: uuid.UUID, child_id: uuid.UUID
    ) -> builtins.list[dict[str, Any]]:
        # builtins.list: the class defines a method named `list`, which otherwise shadows the
        # builtin in this annotation (under `from __future__ import annotations`).
        self._require_child(family_id, child_id)
        return [dump(h) for h in self._history.list_by_child(child_id)]

    def add_reading_history(
        self, family_id: uuid.UUID, child_id: uuid.UUID, body: ReadingHistoryCreate
    ) -> dict[str, Any]:
        self._require_child(family_id, child_id)
        entry = self._history.add(
            ReadingHistory(child_id=child_id, **body.model_dump())
        )
        return dump(entry)

    def update_reading_history(
        self,
        family_id: uuid.UUID,
        child_id: uuid.UUID,
        entry_id: uuid.UUID,
        body: ReadingHistoryUpdate,
    ) -> dict[str, Any]:
        self._require_child(family_id, child_id)
        entry = self._history.get_for_child(entry_id, child_id)
        if entry is None:
            raise NotFoundError
        apply_changes(entry, body.model_dump(exclude_unset=True))
        return dump(self._history.update(entry))

    def delete_reading_history(
        self, family_id: uuid.UUID, child_id: uuid.UUID, entry_id: uuid.UUID
    ) -> None:
        self._require_child(family_id, child_id)
        entry = self._history.get_for_child(entry_id, child_id)
        if entry is None:
            raise NotFoundError
        self._history.delete(entry.id)
