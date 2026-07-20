"""Runtime settings for the accounts service (IdP), read from the environment / .env.

This service is the token ISSUER: it holds the RS256 PRIVATE key and signs access tokens. It also
verifies its own tokens (with the matching PUBLIC key) to protect its CRUD endpoints. The BFF, a
separate service, holds only the public key and never signs.

Kept free of DB imports so the app and its health check can start without a database.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration. Values come from environment variables (or .env)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Allow constructing by field name (not only env alias) so tests/overrides can pass
        # `service_token=...` directly and have it take priority over the environment.
        populate_by_name=True,
    )

    # --- access tokens (RS256; this service signs, and verifies its own) ---
    jwt_algorithm: str = "RS256"
    # Signing key (PEM). Provide inline via JWT_PRIVATE_KEY or a path via JWT_PRIVATE_KEY_PATH.
    jwt_private_key: str | None = None
    jwt_private_key_path: str | None = "keys/private.pem"
    # Verifying key (PEM). Provide inline via JWT_PUBLIC_KEY or a path via JWT_PUBLIC_KEY_PATH.
    jwt_public_key: str | None = None
    jwt_public_key_path: str | None = "keys/public.pem"
    # Claims contract: every issued token carries `iss` and `aud`; verifiers must check both.
    jwt_issuer: str = "book-recommendation-accounts"
    jwt_audience: str = "book-recommendation"
    # Access-token lifetime in seconds (default 1 hour).
    jwt_ttl_seconds: int = 3600
    # Optional `kid` (key id) stamped into the JWT header; lets verifiers select among keys during a
    # future key rotation. None (default) omits the header — a single active key needs no selection.
    jwt_key_id: str | None = None

    # --- refresh tokens (rotating; digest stored, raw returned once in an HttpOnly cookie) ---
    # Absolute refresh-token lifetime in seconds (default 30 days) — the hard cap on a session.
    refresh_ttl_seconds: int = 60 * 60 * 24 * 30
    # Cookie carrying the refresh token. Scoped to /auth so it is only sent to refresh/logout.
    refresh_cookie_name: str = "refresh_token"  # noqa: S105 — cookie name, not a secret
    # Secure=True means the cookie is only sent over HTTPS. Set False for local http-only dev.
    refresh_cookie_secure: bool = True
    # SameSite policy. "lax" suffices for a same-site frontend (no separate CSRF token needed).
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_path: str = "/auth"

    # --- internal (service-to-service) face ---
    # Shared secret the agent presents as `X-Service-Token` to reach /internal/*. REQUIRED (non-
    # empty); the internal face is refused entirely if it is unset.
    service_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ACCOUNTS_SERVICE_TOKEN", "SERVICE_TOKEN"),
    )

    # --- http ---
    # Comma-separated list of allowed CORS origins for the frontend.
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @staticmethod
    def _resolve_key(inline: str | None, path: str | None) -> str | None:
        """Return inline PEM if given, else read the file at `path` if it exists."""
        if inline:
            return inline
        if path and Path(path).is_file():
            return Path(path).read_text(encoding="utf-8")
        return None

    @property
    def private_key(self) -> str:
        """The RS256 signing key (PEM). Raises if not configured."""
        key = self._resolve_key(self.jwt_private_key, self.jwt_private_key_path)
        if not key:
            raise RuntimeError(
                "no JWT private key configured (set JWT_PRIVATE_KEY or JWT_PRIVATE_KEY_PATH)"
            )
        return key

    @property
    def public_key(self) -> str:
        """The RS256 verifying key (PEM). Raises if not configured."""
        key = self._resolve_key(self.jwt_public_key, self.jwt_public_key_path)
        if not key:
            raise RuntimeError(
                "no JWT public key configured (set JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH)"
            )
        return key


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Fails closed: the RS256 keypair must be resolvable (so tokens can be signed and verified) and
    the internal-face service token must be set (so `/internal/*` is protected).
    """
    settings = Settings()
    # Touch the key properties so a missing/unreadable keypair fails fast at startup.
    _ = settings.private_key
    _ = settings.public_key
    if not settings.service_token:
        raise RuntimeError("ACCOUNTS_SERVICE_TOKEN must be set")
    return settings
