"""
license_server/signing.py — Signs every /license/activate response so a
client can tell a genuine answer from this server apart from one forged by
anyone sitting on the network path (DNS hijack, ARP spoof, a malicious
proxy). Ed25519 rather than a shared HMAC secret: the verifying key is
public and safe to embed in the client (see src/licensing/signature.py) --
whoever holds it still can't forge a signature, unlike a shared secret.

LICENSE_SIGNING_PRIVATE_KEY holds the 32-byte seed as hex. Generate a pair
with `python -m license_server.generate_signing_key`.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_FIELD_SEP = "|"


def canonical_payload(license_key: str, hwid: str, tier: str, expires_at: str) -> bytes:
    return _FIELD_SEP.join((license_key, hwid, tier, expires_at)).encode("utf-8")


def load_private_key_from_env() -> Ed25519PrivateKey:
    seed_hex = os.getenv("LICENSE_SIGNING_PRIVATE_KEY", "")
    if not seed_hex:
        raise RuntimeError(
            "LICENSE_SIGNING_PRIVATE_KEY is not set -- generate one with: "
            "python -m license_server.generate_signing_key"
        )
    try:
        seed = bytes.fromhex(seed_hex)
    except ValueError as exc:
        raise RuntimeError("LICENSE_SIGNING_PRIVATE_KEY is not valid hex") from exc
    if len(seed) != 32:
        raise RuntimeError("LICENSE_SIGNING_PRIVATE_KEY must decode to exactly 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(seed)


def sign_activation(
    private_key: Ed25519PrivateKey, *, license_key: str, hwid: str, tier: str, expires_at: str
) -> str:
    payload = canonical_payload(license_key, hwid, tier, expires_at)
    return private_key.sign(payload).hex()
