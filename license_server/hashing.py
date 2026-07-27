"""license_server/hashing.py — One-way hashing shared by key codes and HWIDs.

Both are high-entropy values (a random key, a hardware UUID) rather than
low-entropy human passwords, so a plain SHA-256 digest is the right tool --
no need for a memory-hard KDF (argon2/bcrypt) here.
"""

from __future__ import annotations

import hashlib


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
