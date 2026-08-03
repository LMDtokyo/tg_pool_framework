from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telethon.tl.types import User

from tg_pool.accounts.warmup_policy import WarmupPolicy
from tg_pool.api.pool_guard import PoolAccessGuard
from tg_pool.api.send_by_numbers import (
    PhoneRecipient,
    SendByNumbersManager,
    SendByNumbersOptions,
    normalize_phone,
)
from tg_pool.config import AccountConfig

pytestmark = pytest.mark.unit


def make_account(phone: str) -> AccountConfig:
    return AccountConfig(
        api_id=1,
        api_hash="hash",
        phone=phone,
        session_dir="sessions",
    )


class _FakeRegistry:
    def __init__(self, first_seen_by_phone: dict) -> None:
        self._first_seen_by_phone = first_seen_by_phone

    def get(self, phone: str):
        first_seen = self._first_seen_by_phone.get(phone)
        return None if first_seen is None else SimpleNamespace(first_seen=first_seen)


def test_delay_multiplier_throttles_a_young_account():
    registry = _FakeRegistry({"+100": datetime.now(timezone.utc)})
    policy = WarmupPolicy(duration_days=7, min_multiplier=3.0)
    manager = SendByNumbersManager(
        [make_account("+100")], PoolAccessGuard(), registry=registry, warmup_policy=policy
    )

    assert manager._delay_multiplier("+100") == pytest.approx(3.0)


def test_delay_multiplier_is_one_without_a_warmup_policy():
    manager = SendByNumbersManager([make_account("+100")], PoolAccessGuard())

    assert manager._delay_multiplier("+100") == 1.0


async def test_daily_cap_allows_everything_without_warmup_or_redis():
    manager = SendByNumbersManager([make_account("+100")], PoolAccessGuard())
    assert await manager._daily_cap_allows("+100") is True


def make_options(**overrides) -> SendByNumbersOptions:
    values = {
        "message": "Hello {first_name}, your number is {phone}",
        "media_paths": [],
        "forward_links": [],
        "bot_relay_username": None,
        "bot_relay_message_ids": [],
        "sms_per_account_min": 1,
        "sms_per_account_max": 40,
        "delay_min_sec": 0,
        "delay_max_sec": 0,
        "max_flood_wait_sec": 500,
        "delete_dialog": False,
        "link_preview": True,
        "silent": False,
        "auto_repost": False,
        "remove_imported_contacts": True,
        "pin_message": False,
        "video_note": False,
        "self_destruct_sec": None,
        "schedule_at": None,
        "streams": 1,
        "auto_stop_ban": 0,
        "auto_stop_spamblock": 0,
        "auto_stop_floodwait": 0,
        "repeat_every_hours": None,
        "results_dir": "exports",
    }
    values.update(overrides)
    return SendByNumbersOptions(**values)


def test_normalize_phone_accepts_formatting_and_rejects_invalid_values() -> None:
    assert normalize_phone("1 (555) 123-4567") == "+15551234567"
    assert normalize_phone("+49 170 1234567") == "+491701234567"
    assert normalize_phone("123") is None


def test_assign_recipients_respects_sender_quotas(monkeypatch) -> None:
    monkeypatch.setattr("tg_pool.api.send_by_numbers.random.randint", lambda _a, _b: 1)
    recipients = [
        PhoneRecipient("+15550000001"),
        PhoneRecipient("+15550000002"),
        PhoneRecipient("+15550000003"),
    ]

    assignments = SendByNumbersManager._assign_recipients(
        recipients,
        ["+100", "+200"],
        1,
        1,
    )

    assert [sender for _, sender in assignments] == ["+100", "+200", None]


async def test_start_deduplicates_numbers_and_forwards_complete_options(monkeypatch) -> None:
    manager = SendByNumbersManager([make_account("+100")], PoolAccessGuard())
    run_cycles = AsyncMock()
    monkeypatch.setattr(manager, "_run_cycles", run_cycles)
    monkeypatch.setattr(manager, "_export_results", lambda _run, _dir: "result.xlsx")

    manager.start(
        phone_numbers=["+1 (555) 000-0001", "15550000001"],
        message="Hello",
        sender_phones=["+100"],
        media_paths=["photo.jpg"],
        streams=4,
        auto_stop_ban=2,
        repeat_every_hours=1,
        require_proxy=False,
    )
    await manager._run.task

    run, senders, options = run_cycles.await_args.args
    assert run.recipients == [PhoneRecipient("+15550000001")]
    assert senders == ["+100"]
    assert options.media_paths == ["photo.jpg"]
    assert options.streams == 1
    assert options.auto_stop_ban == 2
    assert options.repeat_every_hours == 1
    assert manager.status()["export_path"] == "result.xlsx"


async def test_send_payload_uses_phone_and_resolved_profile_variables() -> None:
    manager = SendByNumbersManager([], PoolAccessGuard())
    client = MagicMock()
    sent = MagicMock(id=10)
    client.send_message = AsyncMock(return_value=sent)
    peer = User(id=42, first_name="Alice", phone="15550000001")

    result = await manager._send_payload(
        client,
        peer,
        PhoneRecipient("+15550000001"),
        make_options(),
    )

    assert result == [sent]
    assert client.send_message.await_args.args[1] == (
        "Hello Alice, your number is +15550000001"
    )
