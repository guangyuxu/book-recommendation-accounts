"""PolicyService — family reading policies (optionally scoped to one child)."""

from __future__ import annotations

import uuid
from typing import Any

from ..db.models.family import FamilyReadingPolicy
from ..db.repositories import ChildProfileRepository, FamilyReadingPolicyRepository
from ..errors import NotFoundError
from ..schemas import PolicyCreate, PolicyUpdate, dump
from ._util import apply_changes


class PolicyService:
    def __init__(
        self,
        policies: FamilyReadingPolicyRepository,
        children: ChildProfileRepository,
    ) -> None:
        self._policies = policies
        self._children = children

    def list(self, family_id: uuid.UUID) -> list[dict[str, Any]]:
        return [dump(p) for p in self._policies.list_active(family_id)]

    def create(self, family_id: uuid.UUID, body: PolicyCreate) -> dict[str, Any]:
        child_uuid = self._resolve_child(body.child_id, family_id)
        policy = self._policies.add(
            FamilyReadingPolicy(
                family_id=family_id,
                child_id=child_uuid,
                goals=body.goals,
                constraints=body.constraints,
                avoid_topics=body.avoid_topics,
                content_preferences=body.content_preferences,
                notes=body.notes,
                is_active=body.is_active,
            )
        )
        return dump(policy)

    def update(
        self, family_id: uuid.UUID, policy_id: uuid.UUID, body: PolicyUpdate
    ) -> dict[str, Any]:
        policy = self._policies.get_in_family(policy_id, family_id)
        if policy is None:
            raise NotFoundError
        apply_changes(policy, body.model_dump(exclude_unset=True))
        return dump(self._policies.update(policy))

    def delete(self, family_id: uuid.UUID, policy_id: uuid.UUID) -> None:
        policy = self._policies.get_in_family(policy_id, family_id)
        if policy is None:
            raise NotFoundError
        self._policies.delete(policy.id)

    def _resolve_child(
        self, child_id: str | None, family_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Validate an optional policy `child_id` belongs to the family; 404 if not."""
        if child_id is None:
            return None
        try:
            child_uuid = uuid.UUID(child_id)
        except ValueError:
            raise NotFoundError from None
        if self._children.get_in_family(child_uuid, family_id) is None:
            raise NotFoundError
        return child_uuid
