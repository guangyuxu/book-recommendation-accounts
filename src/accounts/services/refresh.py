"""RefreshTokenService — issue / rotate (one-time use) / revoke refresh tokens.

Only the SHA-256 digest is stored (via `RefreshTokenCodec`), mirroring the invite flow. Rotation is
one-time-use: exchanging a token consumes it and mints a new one in the SAME `session_id` lineage.
Presenting an already consumed/revoked token is treated as REUSE and revokes the whole lineage —
this is the theft-detection guarantee. Framework-free; wired in `accounts.providers`.

PII rule: nothing here logs; it handles opaque token strings and UUIDs only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from ..config import Settings
from ..db.models.family import RefreshToken
from ..db.repositories import RefreshTokenRepository
from ..errors import UnauthorizedError
from ..security import RefreshTokenCodec


class RefreshTokenService:
    def __init__(
        self,
        tokens: RefreshTokenRepository,
        codec: RefreshTokenCodec,
        settings: Settings,
    ) -> None:
        self._tokens = tokens
        self._codec = codec
        self._settings = settings

    def issue(
        self,
        *,
        family_id: uuid.UUID,
        family_member_id: uuid.UUID,
        session_id: uuid.UUID | None = None,
    ) -> str:
        """Mint a refresh token; store only its digest. Return the raw token (shown once).

        `session_id` omitted starts a new rotation lineage (login/signup); passing an existing one
        continues that lineage (rotation).
        """
        raw = self._codec.generate()
        expires_at = datetime.now(UTC) + timedelta(
            seconds=self._settings.refresh_ttl_seconds
        )
        self._tokens.add(
            RefreshToken(
                family_id=family_id,
                family_member_id=family_member_id,
                session_id=session_id or uuid.uuid4(),
                token_hash=self._codec.hash(raw),
                expires_at=expires_at,
            )
        )
        return raw

    def rotate(self, raw: str) -> tuple[str, str, str]:
        """Exchange a valid refresh token for a new one. Return (new_raw, family_id, member_id).

        One-time use with reuse detection:
        - unknown digest → 401;
        - already consumed OR revoked → REUSE: revoke the whole lineage, then 401;
        - expired → 401;
        - otherwise consume this token and issue a fresh one in the same lineage.
        """
        row = self._tokens.get_by_token_hash(self._codec.hash(raw))
        if row is None:
            raise UnauthorizedError("invalid refresh token")
        if row.consumed_at is not None or row.revoked_at is not None:
            # A superseded/revoked token being presented means it was likely stolen — burn the
            # whole session so neither the attacker nor the victim can keep using it.
            self._tokens.revoke_session(row.session_id)
            raise UnauthorizedError("refresh token reuse detected")
        if self._is_expired(row):
            raise UnauthorizedError("refresh token expired")

        row.consumed_at = datetime.now(UTC)
        self._tokens.update(row)
        new_raw = self.issue(
            family_id=row.family_id,
            family_member_id=row.family_member_id,
            session_id=row.session_id,
        )
        return new_raw, str(row.family_id), str(row.family_member_id)

    def revoke(self, raw: str) -> None:
        """Revoke the token's lineage (logout). Idempotent: unknown/already-gone tokens no-op."""
        row = self._tokens.get_by_token_hash(self._codec.hash(raw))
        if row is not None:
            self._tokens.revoke_session(row.session_id)

    @staticmethod
    def _is_expired(row: RefreshToken) -> bool:
        """Whether the token's absolute expiry has passed.

        sqlite returns naive datetimes while Postgres returns tz-aware ones; normalize the stored
        value to UTC before comparing so the check works on both backends.
        """
        expires_at = row.expires_at
        if expires_at is None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= datetime.now(UTC)
