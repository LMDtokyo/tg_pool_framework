from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from src.api.pool_guard import PoolAccessGuard
from src.api.send_by_id import (
    IdRecipient,
    SendByIdManager,
    SendByIdOptions,
    load_id_database,
)
from src.config import AccountConfig


def make_account(phone: str) -> AccountConfig:
    return AccountConfig(
        api_id=1,
        api_hash="hash",
        phone=phone,
        session_dir="sessions",
    )


def test_load_txt_database_deduplicates_ids(tmp_path: Path) -> None:
    database = tmp_path / "audience.txt"
    database.write_text(
        "12345,987654,@alice,@donor\n"
        "12345,987654,@alice,@donor\n"
        "67890,,@bob,https://t.me/group\n",
        encoding="utf-8",
    )

    recipients = load_id_database(str(database))

    assert recipients == [
        IdRecipient(
            user_id=12345,
            access_hash=987654,
            username="alice",
            donor="@donor",
        ),
        IdRecipient(
            user_id=67890,
            username="bob",
            donor="https://t.me/group",
        ),
    ]


def test_load_json_database_supports_wrapped_array(tmp_path: Path) -> None:
    database = tmp_path / "audience.json"
    database.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "user_id": 12345,
                        "access_hash": 111,
                        "username": "@alice",
                        "first_name": "Alice",
                        "source": "@group",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    recipients = load_id_database(str(database))

    assert recipients[0].user_id == 12345
    assert recipients[0].access_hash == 111
    assert recipients[0].username == "alice"
    assert recipients[0].first_name == "Alice"
    assert recipients[0].donor == "@group"


def test_load_excel_database_uses_id_and_source_columns(tmp_path: Path) -> None:
    database = tmp_path / "audience.xlsx"
    pd.DataFrame(
        [
            {
                "ID": 12345,
                "Username": "@alice",
                "First name": "Alice",
                "Source": "@group",
            }
        ]
    ).to_excel(database, index=False)

    recipients = load_id_database(str(database))

    assert recipients == [
        IdRecipient(
            user_id=12345,
            username="alice",
            first_name="Alice",
            donor="@group",
        )
    ]


def test_load_database_rejects_empty_file(tmp_path: Path) -> None:
    database = tmp_path / "empty.txt"
    database.write_text("# no recipients\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no valid Telegram user IDs"):
        load_id_database(str(database))


def test_assign_recipients_respects_total_sender_capacity(monkeypatch) -> None:
    monkeypatch.setattr("src.api.send_by_id.random.randint", lambda _a, _b: 2)
    recipients = [IdRecipient(user_id=value) for value in range(1, 7)]

    assignments = SendByIdManager._assign_recipients(
        recipients,
        ["+100", "+200"],
        1,
        3,
    )

    assert [sender for _, sender in assignments] == [
        "+100",
        "+200",
        "+100",
        "+200",
        None,
        None,
    ]


def test_start_validates_message_source(tmp_path: Path) -> None:
    database = tmp_path / "audience.txt"
    database.write_text("12345\n", encoding="utf-8")
    manager = SendByIdManager(
        accounts=[make_account("+100")],
        pool_guard=PoolAccessGuard(),
    )

    with pytest.raises(ValueError, match="Message text, media"):
        manager.start(
            database_path=str(database),
            sender_phones=["+100"],
        )


def make_options(**overrides) -> SendByIdOptions:
    values = {
        "message": "Hello {username}",
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
        "leave_donor_groups": False,
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
    return SendByIdOptions(**values)


async def test_send_payload_personalizes_media_and_applies_file_options() -> None:
    manager = SendByIdManager([], PoolAccessGuard())
    sent = MagicMock(id=55)
    client = MagicMock()
    client.send_file = AsyncMock(return_value=sent)
    peer = MagicMock()

    result = await manager._send_payload(
        client,
        peer,
        IdRecipient(user_id=123, username="alice"),
        make_options(
            media_paths=["clip.mp4"],
            video_note=True,
            self_destruct_sec=60,
            silent=True,
        ),
    )

    assert result == [sent]
    client.send_file.assert_awaited_once_with(
        peer,
        "clip.mp4",
        caption="Hello alice",
        parse_mode="html",
        silent=True,
        schedule=None,
        video_note=True,
        ttl=60,
    )


async def test_scheduled_auto_repost_stages_now_and_schedules_recipient_forward() -> None:
    manager = SendByIdManager([], PoolAccessGuard())
    scheduled_at = datetime.now() + timedelta(hours=1)
    staged = MagicMock(id=77)
    reposted = MagicMock(id=88)
    client = MagicMock()
    client.send_message = AsyncMock(return_value=staged)
    client.forward_messages = AsyncMock(return_value=reposted)
    peer = MagicMock()

    result = await manager._send_payload(
        client,
        peer,
        IdRecipient(user_id=123, username="alice"),
        make_options(auto_repost=True, schedule_at=scheduled_at),
    )

    assert result == [reposted]
    client.send_message.assert_awaited_once_with(
        "me",
        "Hello alice",
        parse_mode="html",
        silent=False,
        link_preview=True,
        schedule=None,
    )
    client.forward_messages.assert_awaited_once_with(
        peer,
        staged,
        from_peer="me",
        silent=False,
        schedule=scheduled_at,
    )


async def test_access_hash_resolves_without_network_lookup() -> None:
    manager = SendByIdManager([], PoolAccessGuard())
    client = MagicMock()
    client.get_entity = AsyncMock()

    peer = await manager._resolve_recipient(
        client,
        IdRecipient(user_id=123, access_hash=456),
        {},
        {},
    )

    assert peer.user_id == 123
    assert peer.access_hash == 456
    client.get_entity.assert_not_awaited()


async def test_manager_runs_job_exports_results_and_releases_pool(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = tmp_path / "audience.csv"
    pd.DataFrame(
        [
            {"id": 123, "access_hash": 1001, "username": "alice"},
            {"id": 456, "access_hash": 1002, "username": "bob"},
        ]
    ).to_csv(database, index=False)
    client = MagicMock()
    client.connect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=True)
    client.send_message = AsyncMock(side_effect=[MagicMock(id=1), MagicMock(id=2)])
    client.disconnect = AsyncMock()
    client.is_connected.return_value = True
    monkeypatch.setattr("src.api.send_by_id.ClientFactory.build", lambda _account: client)
    pool_guard = PoolAccessGuard()
    manager = SendByIdManager([make_account("+100")], pool_guard)

    job_id = manager.start(
        database_path=str(database),
        message="Hello {username}",
        sender_phones=["+100"],
        sms_per_account_min=2,
        sms_per_account_max=2,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    assert manager._run is not None
    await manager._run.task

    status = manager.status()
    assert status["job_id"] == job_id
    assert status["sent"] == 2
    assert status["failed"] == 0
    assert status["finished"] is True
    assert Path(status["export_path"]).is_file()
    assert pool_guard.current_holder is None
    assert client.send_message.await_args_list[0].args[1] == "Hello alice"
    assert client.send_message.await_args_list[1].args[1] == "Hello bob"
