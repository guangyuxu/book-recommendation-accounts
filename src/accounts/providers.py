"""dishka dependency-injection providers — the ONLY module that imports dishka.

Domain classes (services, hashers, token/identity, context loader) stay framework-free: their
constructors take plain collaborators and know nothing about dishka. This module is the single
wiring layer that declares how those objects are built and in which scope they live.

Scopes:
- APP: process-wide singletons (settings, the sessionmaker, and — added in later slices — the
  password hasher / token service / invite codec / identity resolver).
- REQUEST: one per HTTP request (the SQLAlchemy session with its transaction boundary, and — added
  later — the per-request repositories, services, and resolved identity).
"""

from __future__ import annotations

from collections.abc import Generator

from dishka import Provider, Scope, provide
from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from .auth import BearerIdentityResolver, Identity, IdentityResolver
from .config import Settings, get_settings
from .db import SessionLocal
from .db.repositories import (
    ChildProfileRepository,
    ChildReadingProfileRepository,
    FamilyInviteRepository,
    FamilyMemberProfileRepository,
    FamilyMemberRepository,
    FamilyReadingPolicyRepository,
    FamilyRepository,
    ReadingHistoryRepository,
    RefreshTokenRepository,
)
from .security import InviteCodec, PasswordHasher, RefreshTokenCodec, TokenService
from .services import (
    AuthService,
    ChildService,
    FamilyContextLoader,
    FamilyService,
    InviteService,
    MemberService,
    PolicyService,
    RefreshTokenService,
)


class AppProvider(Provider):
    """Process-wide singletons."""

    scope = Scope.APP

    # Stateless collaborators: dishka builds each once from its (parameterless) constructor.
    password_hasher = provide(PasswordHasher)
    invite_codec = provide(InviteCodec)
    refresh_token_codec = provide(RefreshTokenCodec)
    # TokenService needs Settings; dishka auto-wires the constructor from the type hint.
    token_service = provide(TokenService)

    @provide
    def settings(self) -> Settings:
        # Delegate to the existing lru_cache'd factory so there is one source of truth. (Wrapping
        # in a method: dishka cannot introspect the lru_cache wrapper's *args/**kwargs directly.)
        return get_settings()

    @provide
    def identity_resolver(self, tokens: TokenService) -> IdentityResolver:
        # Real bearer verification (RS256) is the single external-face identity path.
        return BearerIdentityResolver(tokens)


class DbProvider(Provider):
    """Database session wiring.

    The REQUEST-scoped `session` is a generator provider owning the transaction boundary — the
    class-based equivalent of the old `session_scope()`. dishka finalizes it by *sending* the
    request's exception (or `None`) back into the generator at the `yield` (it uses `gen.send`, not
    `gen.throw`), so we branch on that value: commit on success, roll back on error, always close.

    Note: FastAPI's exception handlers convert `HTTPException` / `ServiceError` to responses BEFORE
    the request scope closes, so only *unhandled* (500) errors arrive here as a rollback signal.
    That is sufficient because every service validates (raises) BEFORE it writes — no handled error
    ever leaves a partial write to commit (see CLAUDE.md testing rules and the rollback regression
    test).
    """

    @provide(scope=Scope.APP)
    def session_factory(self) -> sessionmaker[Session]:
        return SessionLocal

    @provide(scope=Scope.REQUEST)
    def session(
        self, maker: sessionmaker[Session]
    ) -> Generator[Session, BaseException | None]:
        db = maker()
        error = yield db
        try:
            if error is None:
                db.commit()
            else:
                db.rollback()
        finally:
            db.close()


class RequestProvider(Provider):
    """Per-request objects: repositories, services, and the resolved identity.

    Repositories are built explicitly from the REQUEST-scoped `Session` (advanced-alchemy's
    constructor signature is broad, so an explicit factory is clearer than auto-wiring). Services
    are auto-wired by dishka from their constructor type hints (the repos above plus the APP-scoped
    hasher / token service / invite codec). The resolved `Identity` (external face) is built from
    the incoming `Request` (supplied by `FastapiProvider`) and the configured `IdentityResolver`;
    it is resolved lazily, so the internal face — which never requests it — skips token verification.
    """

    scope = Scope.REQUEST

    # --- repositories (one per request, all on the same Session/transaction) ---
    @provide
    def family_repo(self, session: Session) -> FamilyRepository:
        return FamilyRepository(session=session)

    @provide
    def member_repo(self, session: Session) -> FamilyMemberRepository:
        return FamilyMemberRepository(session=session)

    @provide
    def member_profile_repo(self, session: Session) -> FamilyMemberProfileRepository:
        return FamilyMemberProfileRepository(session=session)

    @provide
    def policy_repo(self, session: Session) -> FamilyReadingPolicyRepository:
        return FamilyReadingPolicyRepository(session=session)

    @provide
    def invite_repo(self, session: Session) -> FamilyInviteRepository:
        return FamilyInviteRepository(session=session)

    @provide
    def refresh_token_repo(self, session: Session) -> RefreshTokenRepository:
        return RefreshTokenRepository(session=session)

    @provide
    def child_repo(self, session: Session) -> ChildProfileRepository:
        return ChildProfileRepository(session=session)

    @provide
    def child_reading_repo(self, session: Session) -> ChildReadingProfileRepository:
        return ChildReadingProfileRepository(session=session)

    @provide
    def reading_history_repo(self, session: Session) -> ReadingHistoryRepository:
        return ReadingHistoryRepository(session=session)

    # --- services (auto-wired from their constructor type hints) ---
    auth_service = provide(AuthService)
    refresh_token_service = provide(RefreshTokenService)
    family_service = provide(FamilyService)
    member_service = provide(MemberService)
    child_service = provide(ChildService)
    policy_service = provide(PolicyService)
    invite_service = provide(InviteService)
    context_loader = provide(FamilyContextLoader)

    @provide
    def identity(self, request: Request, resolver: IdentityResolver) -> Identity:
        return resolver.resolve(request)
