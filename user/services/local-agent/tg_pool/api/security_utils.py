"""
tg_pool/api/security_utils.py — Redacts secret-shaped substrings from text
before it reaches a place a customer might casually share (an exported
.xlsx "Details" column, a bug report). Every manager's catch-all exception
handler does `f"{type(exc).__name__}: {exc}"` for whatever error an
underlying library raises -- most of the time that's a harmless message,
but nothing guarantees a future library version, or an unusual proxy/RPC
failure, won't echo back a credential it was given. This is defense in
depth, not a replacement for not logging secrets in the first place.
"""

from __future__ import annotations

import re

_API_HASH_RE = re.compile(r"\b[0-9a-fA-F]{32}\b")
_CREDENTIAL_URL_RE = re.compile(r"://[^/\s:@]+:[^/\s:@]+@")


def scrub_secrets(text: str) -> str:
    text = _API_HASH_RE.sub("[redacted]", text)
    text = _CREDENTIAL_URL_RE.sub("://[redacted]@", text)
    return text
