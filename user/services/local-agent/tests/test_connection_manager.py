"""
tests/test_connection_manager.py — ClientPool session-encryption wiring.

Only covers the opt-in encryption-at-rest lifecycle added on top of
ClientPool (decrypt on connect, re-encrypt on disconnect) — ClientFactory
itself has no dedicated suite predating this change.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from tg_pool.accounts.session_crypto import ensure_encrypted
from tg_pool.config import AccountConfig, TimingPolicy
from tg_pool.accounts.connection_manager import ClientPool

pytestmark = pytest.mark.unit

FAST_POLICY = TimingPolicy(
    base_delay_sec=0.0, jitter_sec=0.0,
    inter_message_delay_sec=0.0, inter_message_jitter_sec=0.0,
    startup_jitter_max_sec=0.0,
)


def make_mock_client(authorized: bool = True) -> MagicMock:
    client = MagicMock()
    client.connect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=authorized)
    client.is_connected = MagicMock(return_value=True)
    client.disconnect = AsyncMock()
    return client


async def test_connect_decrypts_session_before_building_client(tmp_path):
    key = Fernet.generate_key()
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    account = AccountConfig(
        api_id=1, api_hash="h", phone="+70001", session_dir=str(session_dir)
    )

    plaintext = account.session_path + ".session"
    with open(plaintext, "wb") as f:
        f.write(b"sqlite-bytes")
    ensure_encrypted(account.session_path, key)  # only the .enc form exists now
    assert not os.path.exists(plaintext)

    client = make_mock_client()
    with patch("tg_pool.accounts.connection_manager.ClientFactory.build", return_value=client) as build:
        pool = ClientPool([account], FAST_POLICY, session_encryption_key=key)
        await pool.initialize()

    build.assert_called_once_with(account)
    assert os.path.exists(plaintext), "session should be decrypted before connect()"
    assert len(pool) == 1


async def test_disconnect_reencrypts_session(tmp_path):
    key = Fernet.generate_key()
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    account = AccountConfig(
        api_id=1, api_hash="h", phone="+70002", session_dir=str(session_dir)
    )
    plaintext = account.session_path + ".session"
    with open(plaintext, "wb") as f:
        f.write(b"sqlite-bytes")

    client = make_mock_client()
    with patch("tg_pool.accounts.connection_manager.ClientFactory.build", return_value=client):
        pool = ClientPool([account], FAST_POLICY, session_encryption_key=key)
        await pool.initialize()
        assert os.path.exists(plaintext)

        await pool.close_all()

    assert not os.path.exists(plaintext)
    assert os.path.exists(plaintext + ".enc")


async def test_no_encryption_key_leaves_plaintext_untouched(tmp_path):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    account = AccountConfig(
        api_id=1, api_hash="h", phone="+70003", session_dir=str(session_dir)
    )
    plaintext = account.session_path + ".session"
    with open(plaintext, "wb") as f:
        f.write(b"sqlite-bytes")

    client = make_mock_client()
    with patch("tg_pool.accounts.connection_manager.ClientFactory.build", return_value=client):
        pool = ClientPool([account], FAST_POLICY)  # no session_encryption_key
        await pool.initialize()
        await pool.close_all()

    assert os.path.exists(plaintext)
    assert not os.path.exists(plaintext + ".enc")


async def test_initialize_skips_account_that_times_out(monkeypatch):
    good_account = AccountConfig(api_id=1, api_hash="h", phone="+70004")
    stuck_account = AccountConfig(api_id=1, api_hash="h", phone="+70005")
    good_client = make_mock_client()
    stuck_client = make_mock_client()

    async def never_connect():
        await asyncio.Event().wait()

    stuck_client.connect = AsyncMock(side_effect=never_connect)

    def build_client(account):
        return good_client if account.phone == good_account.phone else stuck_client

    monkeypatch.setenv("CLIENT_CONNECT_TIMEOUT_SEC", "0.01")

    with patch("tg_pool.accounts.connection_manager.ClientFactory.build", side_effect=build_client):
        pool = ClientPool([good_account, stuck_account], FAST_POLICY)
        await asyncio.wait_for(pool.initialize(), timeout=1.0)

    assert pool.get_worker_pairs() == [(good_client, good_account.phone)]
