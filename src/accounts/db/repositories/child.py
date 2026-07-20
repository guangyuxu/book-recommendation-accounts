"""Child-domain repositories, mirroring the agent's child repos.

`get_in_family` is the cross-family isolation gate: a child is only ever fetched together with the
caller's `family_id`, never by `child_id` alone (see CLAUDE.md).
"""

from __future__ import annotations

import uuid

from advanced_alchemy.repository import SQLAlchemySyncRepository

from ..models.child import ChildProfile, ChildReadingProfile, ReadingHistory


class ChildProfileRepository(SQLAlchemySyncRepository[ChildProfile]):
    model_type = ChildProfile

    def list_by_family(self, family_id: uuid.UUID) -> list[ChildProfile]:
        return self.get_many(
            family_id=family_id, order_by=ChildProfile.created_at.asc()
        )

    def get_in_family(
        self, child_id: uuid.UUID, family_id: uuid.UUID
    ) -> ChildProfile | None:
        """Fetch a child ONLY if it belongs to this family (cross-family guard)."""
        return self.get_one_or_none(id=child_id, family_id=family_id)


class ChildReadingProfileRepository(SQLAlchemySyncRepository[ChildReadingProfile]):
    model_type = ChildReadingProfile

    def get_by_child(self, child_id: uuid.UUID) -> ChildReadingProfile | None:
        return self.get_one_or_none(child_id=child_id)


class ReadingHistoryRepository(SQLAlchemySyncRepository[ReadingHistory]):
    model_type = ReadingHistory

    def list_by_child(self, child_id: uuid.UUID) -> list[ReadingHistory]:
        return self.get_many(
            child_id=child_id, order_by=ReadingHistory.created_at.desc()
        )

    def get_for_child(
        self, entry_id: uuid.UUID, child_id: uuid.UUID
    ) -> ReadingHistory | None:
        """Fetch a history entry ONLY if it belongs to this child (ownership guard)."""
        return self.get_one_or_none(id=entry_id, child_id=child_id)
