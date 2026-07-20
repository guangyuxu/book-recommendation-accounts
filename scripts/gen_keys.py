"""Generate an RS256 keypair for local development into `keys/` (gitignored).

    uv run python scripts/gen_keys.py        # or: make keygen

Writes keys/private.pem (PKCS#8) + keys/public.pem (SubjectPublicKeyInfo), matching:
    openssl genpkey -algorithm RSA -pkcs8 -out keys/private.pem -pkeyopt rsa_keygen_bits:2048
    openssl rsa -in keys/private.pem -pubout -out keys/public.pem

Dev convenience only. In production, provision keys via a secrets manager and mount/inject them;
never commit a private key.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)

_KEYS_DIR = Path("keys")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _KEYS_DIR.mkdir(exist_ok=True)
    priv_path = _KEYS_DIR / "private.pem"
    pub_path = _KEYS_DIR / "public.pem"

    if priv_path.exists() or pub_path.exists():
        logger.info("keys already exist in %s/ — leaving them untouched", _KEYS_DIR)
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    priv_path.chmod(0o600)
    logger.info("wrote %s and %s", priv_path, pub_path)


if __name__ == "__main__":
    main()
