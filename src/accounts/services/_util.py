"""Small shared helpers for the service layer."""

from __future__ import annotations

from typing import Any


def apply_changes(model: Any, changes: dict[str, Any]) -> None:
    """Set each `changes` key on `model` (used for PATCH/upsert of already-fetched rows)."""
    for key, value in changes.items():
        setattr(model, key, value)
