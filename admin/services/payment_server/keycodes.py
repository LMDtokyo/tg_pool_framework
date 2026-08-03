from __future__ import annotations

import hashlib
import secrets


def generate_api_key() -> str:
    return f"sk_live_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()


def last4(api_key: str) -> str:
    return api_key.strip()[-4:]
