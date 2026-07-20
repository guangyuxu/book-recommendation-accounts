"""Password hashing and access-token (RS256 JWT) issuance/verification — class-based.

This service is the IdP. Passwords use stdlib PBKDF2-HMAC-SHA256 with a per-user random salt (no
third-party hasher, so there is nothing binary to build and the format is self-describing). Access
tokens are **RS256** JWTs: signed with the PRIVATE key (`TokenService.issue`) and verified with
the PUBLIC key (`TokenService.decode`). The private key never leaves this service; the BFF verifies
with the public key alone. This is the "issuance vs verification separation" the split is built on.

These are framework-free collaborators (no dishka / FastAPI import); they are wired as singletons
in `accounts.providers`. `PasswordHasher` and `InviteCodec` are stateless; `TokenService` holds the
`Settings` (hence the RS256 keypair) it signs/verifies with.

PII rule: nothing here logs; callers pass only opaque strings. Never log a password or a hash.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from .config import Settings

# PBKDF2 parameters. Format stored in the DB: "pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>".
_ALGO = "pbkdf2_sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16

# Entropy for invite codes (bytes fed to secrets.token_urlsafe).
_INVITE_CODE_BYTES = 32

# Entropy for refresh tokens (bytes fed to secrets.token_urlsafe).
_REFRESH_TOKEN_BYTES = 32


class PasswordHasher:
    """PBKDF2 password hashing/verification (stateless)."""

    def hash(self, password: str) -> str:
        """Return a self-describing PBKDF2 hash string for `password`."""
        salt = secrets.token_bytes(_SALT_BYTES)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, _ITERATIONS
        )
        return f"{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"

    def verify(self, password: str, stored: str | None) -> bool:
        """Constant-time check of `password` against a stored PBKDF2 hash.

        Returns False for members without a password set (`stored is None`) or a malformed hash,
        rather than raising, so callers can treat every failure as "bad credentials".
        """
        if not stored:
            return False
        try:
            algo, iterations, salt_hex, hash_hex = stored.split("$")
        except ValueError:
            return False
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)


class InviteCodec:
    """Invite-code generation and digesting (stateless).

    Only the digest is persisted; a presented code is hashed and looked up by its (unique) digest,
    so the raw code never lives in the database. Codes are high-entropy, so a plain digest (no salt)
    is sufficient to key the lookup.
    """

    def generate(self) -> str:
        """Return a fresh high-entropy invite code (URL-safe, never stored raw)."""
        return secrets.token_urlsafe(_INVITE_CODE_BYTES)

    def hash(self, code: str) -> str:
        """Return the SHA-256 hex digest of an invite code."""
        return hashlib.sha256(code.encode("utf-8")).hexdigest()


class RefreshTokenCodec:
    """Refresh-token generation and digesting (stateless).

    Mirrors `InviteCodec`: only the SHA-256 digest is persisted; a presented token is hashed and
    looked up by its (unique) digest, so the raw token never lives in the database. Tokens are
    high-entropy, so a plain digest (no salt) is sufficient to key the lookup.
    """

    def generate(self) -> str:
        """Return a fresh high-entropy refresh token (URL-safe, never stored raw)."""
        return secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)

    def hash(self, token: str) -> str:
        """Return the SHA-256 hex digest of a refresh token."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenService:
    """RS256 access-token issuance and verification, bound to the service `Settings`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def issue(self, *, family_id: str, family_member_id: str) -> str:
        """Issue an RS256-signed access token carrying the verified identity claims.

        Claims contract (shared with the BFF verifier): `sub`, `family_id`, `family_member_id`,
        `iat`, `exp`, plus `iss`/`aud` so the verifier can bind the token to this issuer/audience.
        A `kid` header is added when `jwt_key_id` is configured, so verifiers can select among keys
        during a future key rotation (a single active key needs no selection today).
        """
        settings = self._settings
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            "sub": family_member_id,
            "family_id": family_id,
            "family_member_id": family_member_id,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "exp": now + timedelta(seconds=settings.jwt_ttl_seconds),
        }
        headers = {"kid": settings.jwt_key_id} if settings.jwt_key_id else None
        return jwt.encode(
            claims,
            settings.private_key,
            algorithm=settings.jwt_algorithm,
            headers=headers,
        )

    def decode(self, token: str) -> dict[str, Any]:
        """Verify a token's signature/expiry/issuer/audience and return its claims.

        Raises `jwt.InvalidTokenError` (or a subclass, e.g. `ExpiredSignatureError`) on any failure;
        the auth layer maps that to a 401.
        """
        settings = self._settings
        return jwt.decode(
            token,
            settings.public_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
