"""Request-scoped transaction boundary: the DI session commits on success, rolls back on error.

dishka finalizes the REQUEST-scoped session by sending the request's exception (or None) back into
the generator provider. These tests pin that contract so a future dishka/provider change that
silently commits partial writes on error is caught.
"""

from __future__ import annotations

import pytest
from dishka import Scope
from sqlalchemy.orm import Session

from accounts.container import build_container
from accounts.db.models.family import Family
from accounts.db.repositories import FamilyRepository


def _count() -> int:
    with build_container()(scope=Scope.REQUEST) as request:
        return len(FamilyRepository(session=request.get(Session)).get_many())


def test_request_scope_rolls_back_on_error() -> None:
    with pytest.raises(RuntimeError):
        with build_container()(scope=Scope.REQUEST) as request:
            FamilyRepository(session=request.get(Session)).add(
                Family(family_name="rollback-me"), auto_refresh=False
            )
            raise RuntimeError("boom after a write")
    assert _count() == 0  # the write was rolled back, not committed


def test_request_scope_commits_on_success() -> None:
    with build_container()(scope=Scope.REQUEST) as request:
        FamilyRepository(session=request.get(Session)).add(
            Family(family_name="keep-me"), auto_refresh=False
        )
    assert _count() == 1  # a clean exit committed the write
