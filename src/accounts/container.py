"""dishka container factory, shared by the app entrypoint and the tests.

`build_container` assembles the providers into a sync container (matching the sync
`SQLAlchemySyncRepository` / sync route handlers). Tests build their own container here too — with
an optional `settings` override — so the DI graph is wired in exactly one place.
"""

from __future__ import annotations

from dishka import Container, Provider, Scope, make_container, provide
from dishka.integrations.fastapi import FastapiProvider

from .config import Settings
from .providers import AppProvider, DbProvider, RequestProvider


class _SettingsOverride(Provider):
    """Test seam: replace the APP-scoped `Settings` with an explicit instance.

    dishka providers do not honour FastAPI's `dependency_overrides`, so settings-dependent behavior
    (the service-token guard, key material) is overridden here at the container instead.
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    @provide(scope=Scope.APP, override=True)
    def settings(self) -> Settings:
        return self._settings


def build_container(settings: Settings | None = None) -> Container:
    """Build the DI container.

    `FastapiProvider` exposes the incoming `Request` to REQUEST-scoped providers (used by the
    identity resolver on the external face). Pass `settings` to override configuration in tests.
    """
    providers: list[Provider] = [
        AppProvider(),
        DbProvider(),
        RequestProvider(),
        FastapiProvider(),
    ]
    if settings is not None:
        providers.append(_SettingsOverride(settings))
    return make_container(*providers)
