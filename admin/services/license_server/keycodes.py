"""
license_server/keycodes.py — Human-typeable license key generation and hashing.

Keys are never stored in plaintext: the DB only ever sees sha256(key). The
plaintext is returned once, at generation time, for the admin to hand to the
customer -- exactly like an API token.
"""

from __future__ import annotations

import secrets

from license_server.hashing import hash_secret

# Crockford-ish alphabet: no 0/O, 1/I/L, to avoid transcription errors when a
# customer types the key back in by hand.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_GROUP_LENGTH = 4
_GROUP_COUNT = 4
_PREFIX = "TGPL"


def generate_key_code() -> str:
    """A fresh random key like TGPL-XK4M-9QRT-2VBN-H7WZ (~80 bits of entropy)."""
    groups = [
        "".join(secrets.choice(_ALPHABET) for _ in range(_GROUP_LENGTH))
        for _ in range(_GROUP_COUNT)
    ]
    return "-".join([_PREFIX, *groups])


def normalize_key_code(raw: str) -> str:
    """Uppercase + strip whitespace so lookups aren't case/whitespace-sensitive."""
    return raw.strip().upper()


def hash_key_code(key_code: str) -> str:
    return hash_secret(normalize_key_code(key_code))


def last4(key_code: str) -> str:
    normalized = normalize_key_code(key_code)
    return normalized[-4:] if len(normalized) >= 4 else normalized
