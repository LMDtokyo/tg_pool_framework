"""
license_server/generate_signing_key.py — One-time keypair generation for
response signing (see license_server/signing.py).

Usage:
    python -m license_server.generate_signing_key

Prints the private seed (set as LICENSE_SIGNING_PRIVATE_KEY on the license
server -- never commit it) and the public key (paste into
_PUBLIC_KEY_HEX in src/licensing/signature.py, safe to commit -- it only
lets clients verify signatures, not create them).
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    private_key = Ed25519PrivateKey.generate()
    seed = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    print(f"LICENSE_SIGNING_PRIVATE_KEY={seed.hex()}")
    print(f"public key (for src/licensing/signature.py): {public.hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
