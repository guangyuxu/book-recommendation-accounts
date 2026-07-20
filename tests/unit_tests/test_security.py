"""Password hashing (PasswordHasher) and RS256 JWT issuance/verification (TokenService)."""

from __future__ import annotations

import time

import jwt
import pytest

from accounts.config import Settings
from accounts.security import InviteCodec, PasswordHasher, TokenService

from .conftest import make_keypair


def _settings(**overrides: object) -> Settings:
    priv, pub = make_keypair()
    base: dict[str, object] = {
        "jwt_private_key": priv,
        "jwt_public_key": pub,
        "service_token": "x",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_password_hash_roundtrip() -> None:
    hasher = PasswordHasher()
    stored = hasher.hash("s3cret-password")
    assert stored != "s3cret-password"
    assert hasher.verify("s3cret-password", stored) is True
    assert hasher.verify("wrong", stored) is False


def test_verify_password_rejects_missing_or_malformed() -> None:
    hasher = PasswordHasher()
    assert hasher.verify("x", None) is False
    assert hasher.verify("x", "not-a-valid-hash") is False


def test_invite_codec_digest_is_stable_and_hides_raw_code() -> None:
    codec = InviteCodec()
    code = codec.generate()
    assert code  # non-empty, high-entropy
    digest = codec.hash(code)
    assert digest != code
    # Deterministic: the same code always maps to the same digest (so lookups by digest work).
    assert codec.hash(code) == digest


def test_jwt_roundtrip_carries_claims_and_contract() -> None:
    settings = _settings()
    tokens = TokenService(settings)
    token = tokens.issue(family_id="fam-1", family_member_id="mem-1")
    claims = tokens.decode(token)
    assert claims["family_id"] == "fam-1"
    assert claims["family_member_id"] == "mem-1"
    assert claims["sub"] == "mem-1"
    assert claims["iss"] == settings.jwt_issuer
    assert claims["aud"] == settings.jwt_audience


def test_jwt_rejects_wrong_key() -> None:
    signer = _settings()
    token = TokenService(signer).issue(family_id="f", family_member_id="m")
    # A verifier holding a DIFFERENT public key must reject the signature.
    other = _settings()
    verifier = Settings(  # type: ignore[arg-type]
        jwt_private_key=other.jwt_private_key,
        jwt_public_key=other.jwt_public_key,
        service_token="x",
    )
    with pytest.raises(jwt.InvalidTokenError):
        TokenService(verifier).decode(token)


def test_jwt_rejects_wrong_audience() -> None:
    settings = _settings(jwt_audience="book-recommendation")
    token = TokenService(settings).issue(family_id="f", family_member_id="m")
    verifier = _settings(
        jwt_private_key=settings.jwt_private_key,
        jwt_public_key=settings.jwt_public_key,
        jwt_audience="someone-else",
    )
    with pytest.raises(jwt.InvalidTokenError):
        TokenService(verifier).decode(token)


def test_jwt_expiry() -> None:
    settings = _settings(jwt_ttl_seconds=-1)
    token = TokenService(settings).issue(family_id="f", family_member_id="m")
    time.sleep(0.01)
    with pytest.raises(jwt.ExpiredSignatureError):
        TokenService(settings).decode(token)
