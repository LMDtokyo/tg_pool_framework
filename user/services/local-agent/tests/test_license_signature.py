"""tests/test_license_signature.py — tg_pool/licensing/signature.verify_activation.

Uses a throwaway Ed25519 pair, unrelated to the real key (private half lives
only in the deployed license server's environment; public half is baked
into tg_pool/licensing/signature.py). Generated with
license_server/generate_signing_key.py.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tg_pool.licensing.signature import verify_activation

pytestmark = pytest.mark.unit

_TEST_PRIVATE_HEX = "536d31e2f677ece07053995d7bfe5cc73c5b36a3706f4f402ddd01d5a468bf7e"
_TEST_PUBLIC_HEX = "e2982c3a0dda4a4995e02b48089305c2d4a3227bc66ff85f7a39522834da49f7"


def _sign_activation(private_key, *, license_key, hwid, tier, expires_at):
    payload = "|".join((license_key, hwid, tier, expires_at)).encode("utf-8")
    return private_key.sign(payload).hex()


def _sign(**overrides):
    fields = {
        "license_key": "TGPL-AAAA-BBBB-CCCC-DDDD",
        "hwid": "hwid-1",
        "tier": "month",
        "expires_at": "2026-08-30T00:00:00+00:00",
    }
    fields.update(overrides)
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(_TEST_PRIVATE_HEX))
    return fields, _sign_activation(private_key, **fields)


def test_a_genuine_signature_verifies():
    fields, signature = _sign()
    assert verify_activation(**fields, signature_hex=signature, public_key_hex=_TEST_PUBLIC_HEX) is True


def test_a_tampered_expiry_fails_verification():
    fields, signature = _sign()
    fields["expires_at"] = "2099-01-01T00:00:00+00:00"
    assert verify_activation(**fields, signature_hex=signature, public_key_hex=_TEST_PUBLIC_HEX) is False


def test_a_tampered_tier_fails_verification():
    fields, signature = _sign()
    fields["tier"] = "year"
    assert verify_activation(**fields, signature_hex=signature, public_key_hex=_TEST_PUBLIC_HEX) is False


def test_a_signature_from_the_wrong_key_fails_verification():
    other_key = Ed25519PrivateKey.generate()
    fields = {
        "license_key": "TGPL-AAAA-BBBB-CCCC-DDDD",
        "hwid": "hwid-1",
        "tier": "month",
        "expires_at": "2026-08-30T00:00:00+00:00",
    }
    signature = _sign_activation(other_key, **fields)
    assert verify_activation(**fields, signature_hex=signature, public_key_hex=_TEST_PUBLIC_HEX) is False


def test_malformed_hex_fails_verification_instead_of_raising():
    fields, _ = _sign()
    assert verify_activation(**fields, signature_hex="not-hex!", public_key_hex=_TEST_PUBLIC_HEX) is False
