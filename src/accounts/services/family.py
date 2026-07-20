"""FamilyService — read/update the caller's own family row."""

from __future__ import annotations

import uuid
from typing import Any

from ..db.repositories import FamilyRepository
from ..errors import NotFoundError
from ..schemas import FamilyUpdate, dump
from ._util import apply_changes


class FamilyService:
    def __init__(self, families: FamilyRepository) -> None:
        self._families = families

    def get(self, family_id: uuid.UUID) -> dict[str, Any]:
        family = self._families.get_one_or_none(id=family_id)
        if family is None:
            raise NotFoundError
        return dump(family)

    def update(self, family_id: uuid.UUID, body: FamilyUpdate) -> dict[str, Any]:
        family = self._families.get_one_or_none(id=family_id)
        if family is None:
            raise NotFoundError
        apply_changes(family, body.model_dump(exclude_unset=True))
        return dump(self._families.update(family))
