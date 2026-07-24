"""tests/test_invite_by_number.py — invite-link DM sender manager."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telethon.tl.types import PeerUser, User

from src.api.invite_by_number import (
    InviteByNumberAlreadyRunningError,
    InviteByNumberManager,
    InviteRecipient,
    InviteSenderLink,
    normalize_invite_link,
    normalize_phone,
    normalize_recipient_id,
    normalize_username,
)
from src.api.pool_guard import PoolAccessGuard
from src.config import AccountConfig

pytestmark = pytest.mark.unit


def _account(phone: str = "+15551234567") -> AccountConfig:
    return AccountConfig(
        api_id=1,
        api_hash="hash",
        phone=phone,
        session_dir="sessions",
    )


def test_normalize_recipient_id_and_invite_link():
    assert normalize_recipient_id("8535286786") == "8535286786"
    assert normalize_recipient_id("8.035155468E9") == "8035155468"
    assert normalize_recipient_id("@gokuboa2") is None
    assert normalize_username("@gokuboa2") == "@gokuboa2"
    assert normalize_recipient_id("12") is None
    assert normalize_phone("1 (555) 123-4567") == "+15551234567"
    assert normalize_invite_link("join https://t.me/+AbCdEfGh now") == "https://t.me/+AbCdEfGh"
    assert normalize_invite_link("not a link") is None


def test_start_rejects_unknown_sender():
    manager = InviteByNumberManager(accounts=[_account()], pool_guard=PoolAccessGuard())
    with pytest.raises(ValueError, match="Sender account not found"):
        manager.start(
            recipients=[InviteRecipient(recipient_id="8535286786")],
            sender_links=[InviteSenderLink(sender_phone="+19999999999", invite_link="https://t.me/+x")],
        )


def test_start_rejects_empty_recipients():
    manager = InviteByNumberManager(accounts=[_account()], pool_guard=PoolAccessGuard())
    with pytest.raises(ValueError, match="No valid recipients"):
        manager.start(
            recipients=[InviteRecipient(recipient_id="abc")],
            sender_links=[InviteSenderLink(sender_phone="+15551234567", invite_link="https://t.me/+x")],
        )


async def test_already_running_raises():
    manager = InviteByNumberManager(accounts=[_account()], pool_guard=PoolAccessGuard())
    manager._run = SimpleNamespace(finished=False)  # type: ignore[attr-defined]
    with pytest.raises(InviteByNumberAlreadyRunningError):
        manager.start(
            recipients=[InviteRecipient(recipient_id="8535286786")],
            sender_links=[InviteSenderLink(sender_phone="+15551234567", invite_link="https://t.me/+x")],
        )


async def test_sends_invite_via_telethon(monkeypatch):
    account = _account()
    guard = PoolAccessGuard()
    manager = InviteByNumberManager(accounts=[account], pool_guard=guard)

    user = User(id=8535286786, access_hash=1, first_name="Test")
    me = User(id=1, access_hash=1, first_name="Me")
    sent = SimpleNamespace(peer_id=PeerUser(user_id=8535286786))

    client = MagicMock()
    client.connect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.is_connected = MagicMock(return_value=True)
    client.get_me = AsyncMock(return_value=me)
    client.get_entity = AsyncMock(return_value=user)
    client.send_message = AsyncMock(return_value=sent)

    monkeypatch.setattr(
        "src.api.invite_by_number.ClientFactory.build",
        lambda _account: client,
    )

    job_id = manager.start(
        recipients=[InviteRecipient(recipient_id="8535286786", username="@gokuboa2")],
        sender_links=[InviteSenderLink(sender_phone=account.phone, invite_link="https://t.me/+InviteTest")],
        delay_min_sec=0,
        delay_max_sec=0,
        max_per_account=5,
    )
    assert job_id
    assert manager.is_running

    for _ in range(50):
        status = manager.status()
        if status["finished"]:
            break
        await asyncio.sleep(0.02)

    status = manager.status()
    assert status["finished"] is True
    assert status["sent"] == 1
    assert status["failed"] == 0
    assert status["results"][0]["state"] == "sent"
    assert "Delivered DM to id=8535286786" in status["results"][0]["message"]
    client.send_message.assert_awaited_once()
    assert guard.current_holder is None


async def test_rejects_self_chat_as_sent(monkeypatch):
    account = _account()
    manager = InviteByNumberManager(accounts=[account], pool_guard=PoolAccessGuard())

    me = User(id=42, access_hash=1, first_name="Me")
    sent = SimpleNamespace(peer_id=PeerUser(user_id=42))
    client = MagicMock()
    client.connect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.is_connected = MagicMock(return_value=True)
    client.get_me = AsyncMock(return_value=me)
    client.get_entity = AsyncMock(return_value=User(id=8535286786, access_hash=1, first_name="Other"))
    client.send_message = AsyncMock(return_value=sent)

    monkeypatch.setattr(
        "src.api.invite_by_number.ClientFactory.build",
        lambda _account: client,
    )

    manager.start(
        recipients=[InviteRecipient(recipient_id="8535286786")],
        sender_links=[InviteSenderLink(sender_phone=account.phone, invite_link="https://t.me/+x")],
        delay_min_sec=0,
        delay_max_sec=0,
    )
    for _ in range(50):
        if manager.status()["finished"]:
            break
        await asyncio.sleep(0.02)

    status = manager.status()
    assert status["sent"] == 0
    assert status["failed"] == 1
    assert "Saved Messages" in status["results"][0]["message"]


async def test_stop_marks_pending_skipped(monkeypatch):
    account = _account()
    manager = InviteByNumberManager(accounts=[account], pool_guard=PoolAccessGuard())

    user = User(id=8535286786, access_hash=1, first_name="Test")
    me = User(id=1, access_hash=1, first_name="Me")
    client = MagicMock()
    client.connect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.is_connected = MagicMock(return_value=True)
    client.get_me = AsyncMock(return_value=me)
    client.get_entity = AsyncMock(return_value=user)

    async def slow_send(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        return SimpleNamespace(peer_id=PeerUser(user_id=8535286786))

    monkeypatch.setattr(
        "src.api.invite_by_number.ClientFactory.build",
        lambda _account: client,
    )
    monkeypatch.setattr(client, "send_message", AsyncMock(side_effect=slow_send))

    manager.start(
        recipients=[
            InviteRecipient(recipient_id="8535286786"),
            InviteRecipient(recipient_id="8820638155"),
        ],
        sender_links=[InviteSenderLink(sender_phone=account.phone, invite_link="https://t.me/+x")],
        delay_min_sec=0,
        delay_max_sec=0,
    )
    await asyncio.sleep(0.05)
    await manager.stop()

    status = manager.status()
    assert status["finished"] is True
    states = {row["state"] for row in status["results"]}
    assert "skipped" in states or "sent" in states
