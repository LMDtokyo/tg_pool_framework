"""
src/accounts/session_crypto.py — Encrypt/decrypt Telethon .session files at rest.

.session files are bearer credentials (a live, authorized MTProto auth key) —
leaving them as plaintext SQLite files on disk means anyone who reads the
filesystem can impersonate the account. This is opt-in (SESSION_ENCRYPTION_ENABLED)
so the default dev workflow is unaffected: ClientPool decrypts a session right
before connect() and re-encrypts it (removing the plaintext copy) right after
disconnect(), so plaintext only exists on disk while the process is actually
using it.

Key management: SESSION_ENCRYPTION_KEY is a Fernet key (generate with
`Fernet.generate_key()`). Rotating/storing that key via an external secrets
manager (Vault, SOPS, etc.) is an ops concern, not something this module does.
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

SESSION_SUFFIX = ".session"
ENCRYPTED_SUFFIX = ".session.enc"


def encrypt_file(plaintext_path: str, key: bytes) -> str:
    """Encrypt plaintext_path to plaintext_path + '.enc' and remove the plaintext."""
    with open(plaintext_path, "rb") as f:
        data = f.read()
    token = Fernet(key).encrypt(data)

    encrypted_path = plaintext_path + ".enc"
    with open(encrypted_path, "wb") as f:
        f.write(token)
    os.remove(plaintext_path)
    return encrypted_path


def decrypt_file(encrypted_path: str, key: bytes) -> str:
    """Decrypt encrypted_path (ending in '.enc') back to its plaintext path."""
    with open(encrypted_path, "rb") as f:
        token = f.read()
    data = Fernet(key).decrypt(token)

    plaintext_path = encrypted_path[: -len(".enc")]
    with open(plaintext_path, "wb") as f:
        f.write(data)
    return plaintext_path


def ensure_decrypted(session_path: str, key: bytes) -> None:
    """
    Decrypt the account's session into place if only the encrypted form exists.

    No-op if the plaintext file is already present (already decrypted, or a
    brand-new session that hasn't been encrypted yet).
    """
    plaintext = session_path + SESSION_SUFFIX
    encrypted = session_path + ENCRYPTED_SUFFIX
    if os.path.exists(plaintext) or not os.path.exists(encrypted):
        return
    decrypt_file(encrypted, key)
    logger.debug("Decrypted session at %s", plaintext)


def ensure_encrypted(session_path: str, key: bytes) -> None:
    """Encrypt the account's plaintext session back to .enc, if it exists."""
    plaintext = session_path + SESSION_SUFFIX
    if not os.path.exists(plaintext):
        return
    encrypt_file(plaintext, key)
    logger.debug("Re-encrypted session at %s", plaintext)


def load_key_from_env(var_name: str = "SESSION_ENCRYPTION_KEY") -> bytes:
    """Read a Fernet key from an env var, raising a clear error if missing/invalid."""
    raw = os.getenv(var_name, "")
    if not raw:
        raise ValueError(
            f"{var_name} is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return raw.encode("utf-8")
