from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telethon.tl.functions.contacts import (
    DeleteContactsRequest,
    ImportContactsRequest,
)
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import User, UserStatusOffline

from tg_pool.api.number_checker import (
    NumberCheckRow,
    NumberCheckerManager,
    infer_gender,
    normalize_phone,
)
from tg_pool.api.pool_guard import PoolAccessGuard
from tg_pool.config import AccountConfig


def _account(phone: str = "+15551234567") -> AccountConfig:
    return AccountConfig(
        api_id=1,
        api_hash="hash",
        phone=phone,
        session_dir="sessions",
    )


def _client_for_results() -> MagicMock:
    client = MagicMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.is_connected = MagicMock(return_value=True)
    client.is_user_authorized = AsyncMock(return_value=True)

    found_user = User(
        id=42,
        access_hash=1,
        first_name="Anna",
        last_name="Smith",
        username="anna",
        phone="15550000001",
        status=UserStatusOffline(was_online=None),
    )

    async def request(request):
        if isinstance(request, ImportContactsRequest):
            phone = request.contacts[0].phone
            if phone == "+15550000001":
                return SimpleNamespace(users=[found_user], imported=[object()])
            return SimpleNamespace(users=[], imported=[])
        if isinstance(request, GetFullUserRequest):
            return SimpleNamespace(full_user=SimpleNamespace(about="Profile bio"))
        if isinstance(request, DeleteContactsRequest):
            return SimpleNamespace()
        raise AssertionError(f"Unexpected request: {type(request).__name__}")

    client.side_effect = request
    return client


def _client_with_import_alias() -> MagicMock:
    client = MagicMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.is_connected = MagicMock(return_value=True)
    client.is_user_authorized = AsyncMock(return_value=True)

    imported_alias = User(
        id=77,
        access_hash=2,
        first_name="+15550000003",
        last_name="",
        phone="15550000003",
    )
    actual_profile = User(
        id=77,
        access_hash=2,
        first_name="Maria",
        last_name="Petrova",
        username="maria",
        phone="15550000003",
    )

    async def request(request):
        if isinstance(request, ImportContactsRequest):
            return SimpleNamespace(
                users=[User(id=999, access_hash=3, first_name="Wrong"), imported_alias],
                imported=[
                    SimpleNamespace(
                        client_id=request.contacts[0].client_id,
                        user_id=77,
                    )
                ],
            )
        if isinstance(request, DeleteContactsRequest):
            return SimpleNamespace(users=[actual_profile])
        if isinstance(request, GetFullUserRequest):
            return SimpleNamespace(
                users=[actual_profile],
                full_user=SimpleNamespace(about="Accurate profile"),
            )
        raise AssertionError(f"Unexpected request: {type(request).__name__}")

    client.side_effect = request
    return client


def test_normalize_phone_preserves_supplied_country_digits() -> None:
    assert normalize_phone("1 (555) 123-4567") == "+15551234567"
    assert normalize_phone("8 999 123-45-67") == "+89991234567"
    assert normalize_phone("123") is None


def test_gender_detection_is_conservative() -> None:
    assert infer_gender("Anna") == "female"
    assert infer_gender("Dmitry") == "male"
    assert infer_gender("Qxz") == "unknown"


async def test_checker_persists_found_and_not_found_results(monkeypatch, tmp_path) -> None:
    account = _account()
    manager = NumberCheckerManager(
        [account],
        PoolAccessGuard(),
        usage_database_path=str(tmp_path / "usage.db"),
    )
    client = _client_for_results()
    monkeypatch.setattr(
        "tg_pool.api.number_checker.ClientFactory.build",
        lambda _account: client,
    )

    job_id = manager.start(
        phone_numbers=["+1 555 000 0001", "+1 555 000 0002"],
        sender_phones=[account.phone],
        request_profile_data=True,
        gender_detection=True,
        requests_per_account=2,
        delay_min_sec=0,
        delay_max_sec=0,
        stream_delay_min_sec=0,
        stream_delay_max_sec=0,
        results_dir=str(tmp_path),
    )
    assert job_id

    for _ in range(100):
        if manager.status()["finished"]:
            break
        await asyncio.sleep(0.01)

    status = manager.status()
    assert status["finished"] is True
    assert status["found"] == 1
    assert status["not_found"] == 1
    assert status["pending"] == 0
    assert status["results"][0]["first_name"] == "Anna"
    assert status["results"][0]["bio"] == "Profile bio"
    assert status["results"][0]["gender"] == "female"
    assert status["results"][1]["message"] == "Number not found"
    assert status["database_path"] is None
    assert status["export_path"].endswith("number_checker.xlsx")
    assert not list(tmp_path.glob("*.db"))
    assert client.disconnect.await_count == 1


async def test_checker_uses_exact_mapping_and_profile_name_after_contact_removal(
    monkeypatch, tmp_path
) -> None:
    account = _account()
    manager = NumberCheckerManager(
        [account],
        PoolAccessGuard(),
        usage_database_path=str(tmp_path / "usage.db"),
    )
    client = _client_with_import_alias()
    monkeypatch.setattr(
        "tg_pool.api.number_checker.ClientFactory.build",
        lambda _account: client,
    )

    manager.start(
        phone_numbers=["+15550000003"],
        sender_phones=[account.phone],
        request_profile_data=True,
        requests_per_account=1,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path),
    )
    for _ in range(100):
        if manager.status()["finished"]:
            break
        await asyncio.sleep(0.01)

    result = manager.status()["results"][0]
    assert result["telegram_id"] == "77"
    assert result["first_name"] == "Maria"
    assert result["last_name"] == "Petrova"
    assert result["bio"] == "Accurate profile"


def test_reopening_workbook_resets_interrupted_rows(tmp_path) -> None:
    manager = NumberCheckerManager([], PoolAccessGuard())
    path = tmp_path / "number_checker.xlsx"
    manager._initialize_results(path, ["+15550000001"])  # noqa: SLF001
    manager._set_checking(path, "+15550000001", "+100")  # noqa: SLF001

    manager._initialize_results(path, [])  # noqa: SLF001

    assert manager._pending_phones(path) == ["+15550000001"]  # noqa: SLF001


def test_results_workbook_appends_new_numbers_and_updates_existing_rows(tmp_path) -> None:
    manager = NumberCheckerManager([], PoolAccessGuard())
    path = tmp_path / "number_checker.xlsx"
    manager._initialize_results(  # noqa: SLF001
        path, ["+15550000001", "+15550000002"]
    )
    manager._save_row(  # noqa: SLF001
        path,
        NumberCheckRow(
            phone="+15550000001",
            state="found",
            first_name="Old",
            message="User found",
        ),
    )

    manager._initialize_results(  # noqa: SLF001
        path, ["+15550000001", "+15550000003"]
    )
    manager._save_row(  # noqa: SLF001
        path,
        NumberCheckRow(
            phone="+15550000001",
            state="found",
            first_name="Updated",
            message="User found",
        ),
    )

    rows = manager._read_rows(path)  # noqa: SLF001
    assert [row.phone for row in rows] == [
        "+15550000001",
        "+15550000002",
        "+15550000003",
    ]
    assert rows[0].first_name == "Updated"
    assert path.name == "number_checker.xlsx"
    assert not list(tmp_path.glob("*.db"))
