"""tests/test_session_crypto.py — Session-file encryption at rest."""

import os

import pytest
from cryptography.fernet import Fernet

from src.accounts.session_crypto import (
    decrypt_file,
    encrypt_file,
    ensure_decrypted,
    ensure_encrypted,
    load_key_from_env,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def key() -> bytes:
    return Fernet.generate_key()


def test_encrypt_then_decrypt_round_trips(tmp_path, key):
    plaintext_path = tmp_path / "acc.session"
    plaintext_path.write_bytes(b"sqlite-session-bytes")

    encrypted_path = encrypt_file(str(plaintext_path), key)

    assert not plaintext_path.exists()
    assert os.path.exists(encrypted_path)
    assert encrypted_path.endswith(".enc")

    restored_path = decrypt_file(encrypted_path, key)
    assert restored_path == str(plaintext_path)
    assert plaintext_path.read_bytes() == b"sqlite-session-bytes"


def test_decrypt_with_wrong_key_fails(tmp_path, key):
    plaintext_path = tmp_path / "acc.session"
    plaintext_path.write_bytes(b"secret")
    encrypted_path = encrypt_file(str(plaintext_path), key)

    wrong_key = Fernet.generate_key()
    with pytest.raises(Exception):
        decrypt_file(encrypted_path, wrong_key)


def test_ensure_decrypted_no_op_when_plaintext_already_present(tmp_path, key):
    session_path = str(tmp_path / "acc")
    plaintext = session_path + ".session"
    with open(plaintext, "wb") as f:
        f.write(b"already here")

    ensure_decrypted(session_path, key)  # should not raise, nothing to do
    assert os.path.exists(plaintext)


def test_ensure_decrypted_no_op_when_nothing_exists(tmp_path, key):
    session_path = str(tmp_path / "acc")
    ensure_decrypted(session_path, key)  # brand-new session — no-op
    assert not os.path.exists(session_path + ".session")
    assert not os.path.exists(session_path + ".session.enc")


def test_ensure_encrypted_then_ensure_decrypted_round_trips(tmp_path, key):
    session_path = str(tmp_path / "acc")
    plaintext = session_path + ".session"
    with open(plaintext, "wb") as f:
        f.write(b"sqlite-bytes")

    ensure_encrypted(session_path, key)
    assert not os.path.exists(plaintext)
    assert os.path.exists(session_path + ".session.enc")

    ensure_decrypted(session_path, key)
    assert os.path.exists(plaintext)
    with open(plaintext, "rb") as f:
        assert f.read() == b"sqlite-bytes"


def test_ensure_encrypted_no_op_when_no_plaintext(tmp_path, key):
    session_path = str(tmp_path / "acc")
    ensure_encrypted(session_path, key)  # nothing to encrypt — no-op
    assert not os.path.exists(session_path + ".session.enc")


def test_load_key_from_env_missing_raises(monkeypatch):
    monkeypatch.delenv("SESSION_ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValueError):
        load_key_from_env()


def test_load_key_from_env_reads_value(monkeypatch, key):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", key.decode())
    assert load_key_from_env() == key
