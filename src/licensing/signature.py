"""
src/licensing/signature.py — Verifies the Ed25519 signature on a
/license/activate response (see license_server/signing.py for the signing
side). The public key below is not a secret: publishing it only lets
someone verify signatures, never forge one, so it's committed straight into
source rather than loaded from config.

Generated once via `python -m license_server.generate_signing_key` and
paired with the private key held only by the deployed license server.
"""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_PUBLIC_KEY_HEX = "9f37c7696e8c59e7e2f568890a3161d55006b1024650169ad98ca6a1c5ff49a4"
_DEFAULT_PUBLIC_KEY = Ed25519PublicKey.from_public_bytes(bytes.fromhex(_PUBLIC_KEY_HEX))

_FIELD_SEP = "|"


def _canonical_payload(license_key: str, hwid: str, tier: str, expires_at: str) -> bytes:
    return _FIELD_SEP.join((license_key, hwid, tier, expires_at)).encode("utf-8")


def verify_activation(
    *,
    license_key: str,
    hwid: str,
    tier: str,
    expires_at: str,
    signature_hex: str,
    public_key_hex: str = _PUBLIC_KEY_HEX,
) -> bool:
    """expires_at must be the exact ISO string the server signed (datetime.isoformat()).

    public_key_hex defaults to the real deployed server's key; tests pass a
    throwaway keypair instead so no real key material needs to live in the
    test suite.
    """
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    public_key = (
        _DEFAULT_PUBLIC_KEY
        if public_key_hex == _PUBLIC_KEY_HEX
        else Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    )
    payload = _canonical_payload(license_key, hwid, tier, expires_at)
    try:
        public_key.verify(signature, payload)
        return True
    except InvalidSignature:
        return False
