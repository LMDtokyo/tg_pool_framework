"""
tests/test_tdata_converter.py — Unit tests for tg_pool/tdata_converter.py.

Scenarios:

  find_tdata_folders:
    1.  Returns empty list when no tdata folder exists
    2.  Finds a tdata folder with key_datas at root level
    3.  Finds a tdata folder nested two levels deep
    4.  Finds multiple tdata folders across different subtrees
    5.  Ignores 'tdata' folder without valid markers (not key_datas, no hex dir)
    6.  Finds tdata folder identified by 16-char hex subfolder (no key_datas)
    7.  Raises FileNotFoundError when base_path does not exist
    8.  Does not recurse into found tdata (stops at first tdata level)
    9.  Results are sorted alphabetically

  tdata_to_session:
    10. Success path: TDesktop loaded, ToTelethon called, session path returned
    11. 2FA password forwarded to ToTelethon when provided
    12. NoPasswordProvided → TwoFactorAuthRequiredError
    13. SessionPasswordNeededError → TwoFactorAuthRequiredError
    14. PasswordIncorrect → PasswordHashInvalidError
    15. TelethonPasswordHashInvalidError → PasswordHashInvalidError
    16. Missing tdata path → TDataInvalidError
    17. Path exists but fails _is_valid_tdata → TDataInvalidError
    18. TDesktop constructor raises → TDataInvalidError
    19. TDesktop.isLoaded == False → TDataInvalidError
    20. Output directory is created if absent

  session_to_tdata:
    21. Success path: client connects, ToTDesktop called, SaveTData called
    22. api_id / api_hash variant JSON fields accepted
    23. app_id / app_hash variant JSON fields accepted
    24. Missing session file → FileNotFoundError
    25. Missing json file → FileNotFoundError
    26. JSON missing credentials → TDataInvalidError
    27. Session not authorised → TDataInvalidError
    28. ToTDesktop raises → TDataInvalidError (disconnect still called)
    29. Output directory is created if absent

  Batch tdata → sessions:
    30. Batch converts all items and returns ConversionResult list
    31. Jitter is awaited between accounts (not before the first)
    32. Failed items captured without raising
    33. Batch truncated at 50 items

  Batch sessions → tdata:
    34. Batch converts all items with jitter
    35. Failures captured without raising

  ConversionResult:
    36. __str__ shows OK for success
    37. __str__ shows FAIL for failure
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest

from tg_pool.proxy.tdata_converter import (
    ConversionResult,
    PasswordHashInvalidError,
    TDataFingerprint,
    TDataInvalidError,
    TDataSessionResult,
    TDataConverter,
    TwoFactorAuthRequiredError,
    find_tdata_folders,
)

FAKE_API = MagicMock()
FAKE_API.api_id = 2040
FAKE_API.api_hash = "b18441a1ff607e10a989891a5462e627"
FAKE_API.device_model = "Desktop"
FAKE_API.system_version = "Windows 10"
FAKE_API.app_version = "3.4.3 x64"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_tdata(base: Path, name: str = "tdata", with_key: bool = True) -> Path:
    """Create a tdata folder that passes _is_valid_tdata."""
    td = base / name
    td.mkdir(parents=True, exist_ok=True)
    if with_key:
        (td / "key_datas").write_bytes(b"\x00" * 16)
    return td


def make_hex_tdata(base: Path) -> Path:
    """Create a tdata folder identifiable only by its hex subfolder."""
    td = base / "tdata"
    td.mkdir(parents=True, exist_ok=True)
    hex_dir = td / "D877F783D5D3EF8C"
    hex_dir.mkdir()
    return td


def make_session_json(dir_: Path, api_id: int = 12345, api_hash: str = "a" * 32,
                      key_name: str = "app") -> tuple[Path, Path]:
    """Create .session (empty) + .json sidecar."""
    session = dir_ / "account.session"
    session.write_bytes(b"")
    payload = (
        {"app_id": api_id, "app_hash": api_hash, "phone": "+79001234567"}
        if key_name == "app"
        else {"api_id": api_id, "api_hash": api_hash, "phone": "+79001234567"}
    )
    j = dir_ / "account.json"
    j.write_text(json.dumps(payload))
    return session, j


# ---------------------------------------------------------------------------
# find_tdata_folders
# ---------------------------------------------------------------------------

class TestFindTdataFolders:
    def test_empty_when_no_tdata(self, tmp_path):
        (tmp_path / "some_dir").mkdir()
        assert find_tdata_folders(str(tmp_path)) == []

    def test_finds_root_level_tdata_with_key(self, tmp_path):
        make_tdata(tmp_path)
        result = find_tdata_folders(str(tmp_path))
        assert len(result) == 1
        assert result[0].endswith("tdata")

    def test_finds_phone_named_tdata_root(self, tmp_path):
        td = tmp_path / "13098449992"
        td.mkdir()
        (td / "key_datas").write_bytes(b"key")

        assert find_tdata_folders(str(td)) == [str(td.resolve())]

    def test_finds_phone_named_tdata_below_selected_parent(self, tmp_path):
        td = tmp_path / "13098449992"
        td.mkdir()
        (td / "key_datas").write_bytes(b"key")

        assert find_tdata_folders(str(tmp_path)) == [str(td.resolve())]

    def test_finds_nested_tdata(self, tmp_path):
        nested = tmp_path / "level1" / "level2"
        nested.mkdir(parents=True)
        make_tdata(nested)
        result = find_tdata_folders(str(tmp_path))
        assert len(result) == 1

    def test_finds_multiple_tdata(self, tmp_path):
        make_tdata(tmp_path / "acc1")
        make_tdata(tmp_path / "acc2")
        result = find_tdata_folders(str(tmp_path))
        assert len(result) == 2

    def test_ignores_empty_tdata_folder(self, tmp_path):
        td = tmp_path / "tdata"
        td.mkdir()
        # No key_datas, no hex dir → invalid
        result = find_tdata_folders(str(tmp_path))
        assert result == []

    def test_finds_tdata_by_hex_subfolder(self, tmp_path):
        make_hex_tdata(tmp_path)
        result = find_tdata_folders(str(tmp_path))
        assert len(result) == 1

    def test_raises_when_base_not_found(self, tmp_path):
        missing = str(tmp_path / "does_not_exist")
        with pytest.raises(FileNotFoundError):
            find_tdata_folders(missing)

    def test_does_not_recurse_into_tdata(self, tmp_path):
        outer = make_tdata(tmp_path)
        # Create a nested tdata inside the first one — should NOT be found
        inner_td = outer / "inner" / "tdata"
        inner_td.mkdir(parents=True)
        (inner_td / "key_datas").write_bytes(b"\x00")
        result = find_tdata_folders(str(tmp_path))
        # Only the outer tdata should appear
        assert len(result) == 1

    def test_results_sorted(self, tmp_path):
        make_tdata(tmp_path / "zzz")
        make_tdata(tmp_path / "aaa")
        result = find_tdata_folders(str(tmp_path))
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# tdata_to_session
# ---------------------------------------------------------------------------

def _mock_telethon_client(phone: str = "79001234567") -> MagicMock:
    client = MagicMock()
    client.disconnect = AsyncMock()
    client.get_me = AsyncMock(return_value=MagicMock(phone=phone))
    return client


def _mock_tdesktop(is_loaded=True, accounts_count=1, to_telethon_client=None, accounts=None):
    """Build a properly mocked TDesktop instance."""
    if to_telethon_client is None:
        to_telethon_client = _mock_telethon_client()

    instance = MagicMock()
    instance.isLoaded = MagicMock(return_value=is_loaded)  # isLoaded() is a method, not a property
    instance.accountsCount = accounts_count
    instance.api = FAKE_API
    instance.ToTelethon = AsyncMock(return_value=to_telethon_client)
    instance.accounts = accounts if accounts is not None else [instance]
    return instance


def _mock_account(client=None, api=None, phone="79001234567"):
    """Build a mocked opentele Account (one entry of TDesktop.accounts)."""
    if client is None:
        client = _mock_telethon_client(phone=phone)
    account = MagicMock()
    account.api = api or FAKE_API
    account.ToTelethon = AsyncMock(return_value=client)
    return account


class TestTdataToSession:
    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_phone_named_root_uses_phone_as_session_name(self, MockTDesktop, tmp_path):
        td = tmp_path / "13098449992"
        td.mkdir()
        (td / "key_datas").write_bytes(b"key")
        MockTDesktop.return_value = _mock_tdesktop()

        result = await TDataConverter().tdata_to_session(str(td), str(tmp_path / "out"))

        assert result.session_path.name == "13098449992"

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_success_path(self, MockTDesktop, tmp_path):
        td = make_tdata(tmp_path / "alice")
        out = tmp_path / "sessions"

        mock_inst = _mock_tdesktop()
        MockTDesktop.return_value = mock_inst

        converter = TDataConverter()
        result = await converter.tdata_to_session(str(td), str(out))

        MockTDesktop.assert_called_once_with(str(td))
        mock_inst.ToTelethon.assert_awaited_once_with(
            session=ANY, flag=ANY, password=None
        )
        assert out.exists()
        assert isinstance(result, TDataSessionResult)
        assert isinstance(result.session_path, Path)
        assert result.phone == "+79001234567"
        assert result.fingerprint.api_id == FAKE_API.api_id
        assert result.fingerprint.api_hash == FAKE_API.api_hash
        assert result.fingerprint.device_model == FAKE_API.device_model
        assert result.fingerprint.system_version == FAKE_API.system_version
        assert result.fingerprint.app_version == FAKE_API.app_version

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_password_forwarded(self, MockTDesktop, tmp_path):
        td = make_tdata(tmp_path / "bob")
        out = tmp_path / "sessions"
        mock_inst = _mock_tdesktop()
        MockTDesktop.return_value = mock_inst

        converter = TDataConverter()
        await converter.tdata_to_session(str(td), str(out), password="s3cr3t")

        mock_inst.ToTelethon.assert_awaited_once_with(
            session=ANY, flag=ANY, password="s3cr3t"
        )

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_no_password_raises_two_factor_required(self, MockTDesktop, tmp_path):
        from opentele import exception as ote_exc
        td = make_tdata(tmp_path / "user")
        out = tmp_path / "sessions"

        mock_inst = _mock_tdesktop()
        mock_inst.ToTelethon = AsyncMock(side_effect=ote_exc.NoPasswordProvided(""))
        MockTDesktop.return_value = mock_inst

        with pytest.raises(TwoFactorAuthRequiredError):
            await TDataConverter().tdata_to_session(str(td), str(out))

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_session_password_needed_maps_to_two_factor(self, MockTDesktop, tmp_path):
        from telethon.errors import SessionPasswordNeededError
        td = make_tdata(tmp_path / "user2")
        out = tmp_path / "sessions"

        mock_inst = _mock_tdesktop()
        mock_inst.ToTelethon = AsyncMock(side_effect=SessionPasswordNeededError(request=None))
        MockTDesktop.return_value = mock_inst

        with pytest.raises(TwoFactorAuthRequiredError):
            await TDataConverter().tdata_to_session(str(td), str(out))

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_wrong_password_raises_hash_invalid(self, MockTDesktop, tmp_path):
        from opentele import exception as ote_exc
        td = make_tdata(tmp_path / "user3")
        out = tmp_path / "sessions"

        mock_inst = _mock_tdesktop()
        mock_inst.ToTelethon = AsyncMock(side_effect=ote_exc.PasswordIncorrect(""))
        MockTDesktop.return_value = mock_inst

        with pytest.raises(PasswordHashInvalidError):
            await TDataConverter().tdata_to_session(str(td), str(out), password="wrong")

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_telethon_password_hash_invalid_maps(self, MockTDesktop, tmp_path):
        from telethon.errors import PasswordHashInvalidError as TErr
        td = make_tdata(tmp_path / "user4")
        out = tmp_path / "sessions"

        mock_inst = _mock_tdesktop()
        mock_inst.ToTelethon = AsyncMock(side_effect=TErr(request=None))
        MockTDesktop.return_value = mock_inst

        with pytest.raises(PasswordHashInvalidError):
            await TDataConverter().tdata_to_session(str(td), str(out), password="x")

    async def test_missing_path_raises_invalid(self, tmp_path):
        with pytest.raises(TDataInvalidError, match="not found"):
            await TDataConverter().tdata_to_session(
                str(tmp_path / "nonexistent"), str(tmp_path / "out")
            )

    async def test_invalid_tdata_structure_raises(self, tmp_path):
        td = tmp_path / "tdata"
        td.mkdir()
        # No key_datas, no hex dir → invalid
        with pytest.raises(TDataInvalidError, match="valid tdata"):
            await TDataConverter().tdata_to_session(str(td), str(tmp_path / "out"))

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_tdesktop_constructor_error_raises_invalid(self, MockTDesktop, tmp_path):
        td = make_tdata(tmp_path / "broken")
        out = tmp_path / "sessions"
        MockTDesktop.side_effect = RuntimeError("disk error")

        with pytest.raises(TDataInvalidError, match="Failed to load"):
            await TDataConverter().tdata_to_session(str(td), str(out))

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_not_loaded_raises_invalid(self, MockTDesktop, tmp_path):
        td = make_tdata(tmp_path / "empty")
        out = tmp_path / "sessions"

        mock_inst = _mock_tdesktop(is_loaded=False)
        MockTDesktop.return_value = mock_inst

        with pytest.raises(TDataInvalidError, match="could not load"):
            await TDataConverter().tdata_to_session(str(td), str(out))

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_output_dir_created(self, MockTDesktop, tmp_path):
        td = make_tdata(tmp_path / "acc")
        out = tmp_path / "deep" / "nested" / "sessions"

        MockTDesktop.return_value = _mock_tdesktop()
        await TDataConverter().tdata_to_session(str(td), str(out))
        assert out.exists()

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_flood_wait_is_not_masked_as_invalid_tdata(self, MockTDesktop, tmp_path):
        """A FloodWaitError mid-conversion must propagate as-is, not become TDataInvalidError."""
        from telethon.errors import FloodWaitError

        td = make_tdata(tmp_path / "flooded")
        out = tmp_path / "sessions"
        mock_inst = _mock_tdesktop()
        mock_inst.ToTelethon = AsyncMock(side_effect=FloodWaitError(request=None))
        MockTDesktop.return_value = mock_inst

        with pytest.raises(FloodWaitError):
            await TDataConverter().tdata_to_session(str(td), str(out))

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_opentele_exception_is_wrapped_not_left_raw(self, MockTDesktop, tmp_path):
        """
        Regression: opentele.exception.OpenTeleException subclasses BaseException
        directly, not Exception (confirmed via OpenTeleException.__mro__) -- a
        bare `except Exception` around TDesktop construction silently let these
        propagate raw and uncaught instead of becoming TDataInvalidError, exactly
        as would happen loading a real but corrupted/incompatible tdata folder
        (opentele raises TFileNotFound from its own Storage.ReadFile()).
        """
        from opentele.exception import TFileNotFound

        td = make_tdata(tmp_path / "corrupted")
        out = tmp_path / "sessions"
        MockTDesktop.side_effect = TFileNotFound("Could not open key_data")

        with pytest.raises(TDataInvalidError, match="Failed to load tdata"):
            await TDataConverter().tdata_to_session(str(td), str(out))


# ---------------------------------------------------------------------------
# list_tdata_accounts / tdata_to_sessions_all (multi-account tdata)
# ---------------------------------------------------------------------------

class TestMultiAccountTdata:
    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_list_tdata_accounts_returns_all(self, MockTDesktop, tmp_path):
        td = make_tdata(tmp_path / "multi")
        accounts = [_mock_account(), _mock_account(), _mock_account()]
        MockTDesktop.return_value = _mock_tdesktop(accounts_count=3, accounts=accounts)

        result = await TDataConverter().list_tdata_accounts(str(td))

        assert result == accounts

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_list_tdata_accounts_invalid_folder_raises(self, MockTDesktop, tmp_path):
        td = tmp_path / "tdata"
        td.mkdir()  # no key_datas, no hex dir -> invalid
        with pytest.raises(TDataInvalidError):
            await TDataConverter().list_tdata_accounts(str(td))

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_converts_every_account_to_its_own_session(self, MockTDesktop, tmp_path):
        td = make_tdata(tmp_path / "multi")
        out = tmp_path / "sessions"

        api_1 = MagicMock(api_id=111, api_hash="h1", device_model="Desktop",
                           system_version="Windows 10", app_version="1.0")
        api_2 = MagicMock(api_id=222, api_hash="h2", device_model="Desktop",
                           system_version="Windows 10", app_version="1.0")
        accounts = [
            _mock_account(api=api_1, phone="79001111111"),
            _mock_account(api=api_2, phone="79002222222"),
        ]
        MockTDesktop.return_value = _mock_tdesktop(accounts_count=2, accounts=accounts)

        results = await TDataConverter().tdata_to_sessions_all(str(td), str(out))

        assert len(results) == 2
        assert results[0].fingerprint.api_id == 111
        assert results[1].fingerprint.api_id == 222
        assert results[0].phone == "+79001111111"
        assert results[1].phone == "+79002222222"
        # Distinct session filenames for a multi-account folder
        assert results[0].session_path != results[1].session_path
        assert results[0].session_path.name.endswith("_acc0")
        assert results[1].session_path.name.endswith("_acc1")
        for account in accounts:
            account.ToTelethon.assert_awaited_once()

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_single_account_keeps_plain_session_name(self, MockTDesktop, tmp_path):
        td = make_tdata(tmp_path / "single")
        out = tmp_path / "sessions"
        accounts = [_mock_account()]
        MockTDesktop.return_value = _mock_tdesktop(accounts_count=1, accounts=accounts)

        results = await TDataConverter().tdata_to_sessions_all(str(td), str(out))

        assert len(results) == 1
        assert "_acc" not in results[0].session_path.name

    @patch("tg_pool.proxy.tdata_converter.TDesktop")
    async def test_2fa_required_on_one_of_several_accounts(self, MockTDesktop, tmp_path):
        from opentele import exception as ote_exc

        td = make_tdata(tmp_path / "multi")
        out = tmp_path / "sessions"
        good_account = _mock_account()
        locked_account = _mock_account()
        locked_account.ToTelethon = AsyncMock(side_effect=ote_exc.NoPasswordProvided(""))
        MockTDesktop.return_value = _mock_tdesktop(
            accounts_count=2, accounts=[good_account, locked_account]
        )

        with pytest.raises(TwoFactorAuthRequiredError):
            await TDataConverter().tdata_to_sessions_all(str(td), str(out))


# ---------------------------------------------------------------------------
# session_to_tdata
# ---------------------------------------------------------------------------

def _mock_opentele_client(authorized=True, me_phone="79001234567"):
    """Build a mocked OpenteleClient."""
    mock_me = MagicMock()
    mock_me.phone = me_phone

    client = MagicMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=authorized)
    client.get_me = AsyncMock(return_value=mock_me)

    mock_tdesktop = MagicMock()
    mock_tdesktop.SaveTData = MagicMock(return_value=True)
    client.ToTDesktop = AsyncMock(return_value=mock_tdesktop)

    return client, mock_tdesktop


class TestSessionToTdata:
    @patch("tg_pool.proxy.tdata_converter.OpenteleClient")
    async def test_success_path(self, MockClient, tmp_path):
        session, j = make_session_json(tmp_path)
        out = tmp_path / "tdata_out"

        mock_client, mock_tdesktop = _mock_opentele_client()
        MockClient.return_value = mock_client

        converter = TDataConverter()
        result = await converter.session_to_tdata(str(session), str(j), str(out))

        mock_client.connect.assert_awaited_once()
        mock_client.ToTDesktop.assert_awaited_once()
        mock_tdesktop.SaveTData.assert_called_once_with(str(out))
        mock_client.disconnect.assert_awaited_once()
        assert result == out

    @patch("tg_pool.proxy.tdata_converter.OpenteleClient")
    async def test_api_id_api_hash_json_variant(self, MockClient, tmp_path):
        session, j = make_session_json(tmp_path, key_name="api")
        out = tmp_path / "out"

        mock_client, _ = _mock_opentele_client()
        MockClient.return_value = mock_client

        await TDataConverter().session_to_tdata(str(session), str(j), str(out))
        # api_id and api_hash are read without error
        MockClient.assert_called_once_with(ANY, 12345, "a" * 32)

    @patch("tg_pool.proxy.tdata_converter.OpenteleClient")
    async def test_app_id_app_hash_json_variant(self, MockClient, tmp_path):
        session, j = make_session_json(tmp_path, key_name="app")
        out = tmp_path / "out"

        mock_client, _ = _mock_opentele_client()
        MockClient.return_value = mock_client

        await TDataConverter().session_to_tdata(str(session), str(j), str(out))
        MockClient.assert_called_once_with(ANY, 12345, "a" * 32)

    async def test_missing_session_raises(self, tmp_path):
        j = tmp_path / "creds.json"
        j.write_text(json.dumps({"app_id": 1, "app_hash": "x"}))
        with pytest.raises(FileNotFoundError, match="Session file"):
            await TDataConverter().session_to_tdata(
                str(tmp_path / "ghost.session"), str(j), str(tmp_path / "out")
            )

    async def test_missing_json_raises(self, tmp_path):
        s = tmp_path / "session.session"
        s.write_bytes(b"")
        with pytest.raises(FileNotFoundError, match="JSON credentials"):
            await TDataConverter().session_to_tdata(
                str(s), str(tmp_path / "nope.json"), str(tmp_path / "out")
            )

    async def test_bad_json_raises_invalid(self, tmp_path):
        s = tmp_path / "account.session"
        s.write_bytes(b"")
        j = tmp_path / "account.json"
        j.write_text(json.dumps({"phone": "+7"}))  # no credentials

        with pytest.raises(TDataInvalidError, match="app_id"):
            await TDataConverter().session_to_tdata(str(s), str(j), str(tmp_path / "out"))

    @patch("tg_pool.proxy.tdata_converter.OpenteleClient")
    async def test_unauthorised_session_raises_invalid(self, MockClient, tmp_path):
        session, j = make_session_json(tmp_path)
        out = tmp_path / "out"

        mock_client, _ = _mock_opentele_client(authorized=False)
        MockClient.return_value = mock_client

        with pytest.raises(TDataInvalidError, match="not authorised"):
            await TDataConverter().session_to_tdata(str(session), str(j), str(out))

        mock_client.disconnect.assert_awaited_once()

    @patch("tg_pool.proxy.tdata_converter.OpenteleClient")
    async def test_to_tdesktop_error_calls_disconnect(self, MockClient, tmp_path):
        session, j = make_session_json(tmp_path)
        out = tmp_path / "out"

        mock_client, _ = _mock_opentele_client()
        mock_client.ToTDesktop = AsyncMock(side_effect=RuntimeError("network"))
        MockClient.return_value = mock_client

        with pytest.raises(TDataInvalidError):
            await TDataConverter().session_to_tdata(str(session), str(j), str(out))

        # disconnect must always be called
        mock_client.disconnect.assert_awaited_once()

    @patch("tg_pool.proxy.tdata_converter.OpenteleClient")
    async def test_output_dir_created(self, MockClient, tmp_path):
        session, j = make_session_json(tmp_path)
        out = tmp_path / "a" / "b" / "c"

        mock_client, _ = _mock_opentele_client()
        MockClient.return_value = mock_client

        await TDataConverter().session_to_tdata(str(session), str(j), str(out))
        assert out.exists()


# ---------------------------------------------------------------------------
# Batch: tdata → sessions
# ---------------------------------------------------------------------------

def _make_session_result(path: Path) -> TDataSessionResult:
    return TDataSessionResult(
        session_path=path,
        fingerprint=TDataFingerprint(
            api_id=FAKE_API.api_id,
            api_hash=FAKE_API.api_hash,
            device_model=FAKE_API.device_model,
            system_version=FAKE_API.system_version,
            app_version=FAKE_API.app_version,
        ),
    )


class TestBatchTdata:
    @patch("tg_pool.proxy.tdata_converter.asyncio.sleep", new_callable=AsyncMock)
    @patch.object(TDataConverter, "tdata_to_session")
    async def test_all_items_processed(self, mock_convert, mock_sleep, tmp_path):
        mock_convert.return_value = _make_session_result(tmp_path / "out" / "session")

        paths = [str(tmp_path / f"acc{i}" / "tdata") for i in range(3)]
        results = await TDataConverter().convert_batch_tdata(paths, str(tmp_path / "out"))

        assert len(results) == 3
        assert all(r.success for r in results)
        assert results[0].api_id == FAKE_API.api_id

    @patch("tg_pool.proxy.tdata_converter.asyncio.sleep", new_callable=AsyncMock)
    @patch.object(TDataConverter, "tdata_to_session")
    async def test_jitter_not_called_before_first_item(self, mock_convert, mock_sleep, tmp_path):
        mock_convert.return_value = _make_session_result(tmp_path / "s")
        paths = [str(tmp_path / f"acc{i}") for i in range(3)]
        await TDataConverter().convert_batch_tdata(paths, str(tmp_path / "out"))
        # sleep called N-1 times (between items, not before the first)
        assert mock_sleep.call_count == len(paths) - 1

    @patch("tg_pool.proxy.tdata_converter.asyncio.sleep", new_callable=AsyncMock)
    @patch.object(TDataConverter, "tdata_to_session")
    async def test_failures_captured_without_raising(self, mock_convert, mock_sleep, tmp_path):
        mock_convert.side_effect = TDataInvalidError("boom")
        paths = [str(tmp_path / "bad")]
        results = await TDataConverter().convert_batch_tdata(paths, str(tmp_path / "out"))
        assert len(results) == 1
        assert not results[0].success
        assert "boom" in results[0].error

    @patch("tg_pool.proxy.tdata_converter.asyncio.sleep", new_callable=AsyncMock)
    @patch.object(TDataConverter, "tdata_to_session")
    async def test_truncated_at_50(self, mock_convert, mock_sleep, tmp_path):
        mock_convert.return_value = _make_session_result(tmp_path / "s")
        paths = [str(tmp_path / f"acc{i}") for i in range(60)]
        results = await TDataConverter().convert_batch_tdata(paths, str(tmp_path / "out"))
        assert len(results) == 50
        assert mock_convert.call_count == 50

    @patch("tg_pool.proxy.tdata_converter.asyncio.sleep", new_callable=AsyncMock)
    @patch.object(TDataConverter, "tdata_to_sessions_all")
    async def test_all_accounts_flag_uses_tdata_to_sessions_all(self, mock_convert, mock_sleep, tmp_path):
        mock_convert.return_value = [
            _make_session_result(tmp_path / "out" / "s_acc0"),
            _make_session_result(tmp_path / "out" / "s_acc1"),
        ]
        paths = [str(tmp_path / "acc0" / "tdata")]

        results = await TDataConverter().convert_batch_tdata(
            paths, str(tmp_path / "out"), all_accounts=True,
        )

        mock_convert.assert_awaited_once()
        assert len(results) == 2  # one input path -> two accounts -> two results
        assert all(r.success for r in results)


# ---------------------------------------------------------------------------
# Batch: sessions → tdata
# ---------------------------------------------------------------------------

class TestBatchSessions:
    @patch("tg_pool.proxy.tdata_converter.asyncio.sleep", new_callable=AsyncMock)
    @patch.object(TDataConverter, "session_to_tdata")
    async def test_all_items_processed(self, mock_convert, mock_sleep, tmp_path):
        mock_convert.return_value = tmp_path / "out" / "tdata"

        configs = [(f"s{i}", f"j{i}", f"acc{i}") for i in range(3)]
        results = await TDataConverter().convert_batch_sessions(configs, str(tmp_path / "out"))

        assert len(results) == 3
        assert all(r.success for r in results)

    @patch("tg_pool.proxy.tdata_converter.asyncio.sleep", new_callable=AsyncMock)
    @patch.object(TDataConverter, "session_to_tdata")
    async def test_failures_captured(self, mock_convert, mock_sleep, tmp_path):
        mock_convert.side_effect = TDataInvalidError("bad session")
        configs = [("s", "j", "out")]
        results = await TDataConverter().convert_batch_sessions(configs, str(tmp_path))
        assert not results[0].success
        assert "bad session" in results[0].error


# ---------------------------------------------------------------------------
# ConversionResult
# ---------------------------------------------------------------------------

class TestConversionResult:
    def test_str_success(self):
        r = ConversionResult(source="/tdata", output="/out/s", success=True)
        assert "OK" in str(r)
        assert "/tdata" in str(r)

    def test_str_failure(self):
        r = ConversionResult(source="/tdata", success=False, error="no 2fa")
        assert "FAIL" in str(r)
        assert "no 2fa" in str(r)

    def test_repr_does_not_leak_api_hash(self):
        """
        Regression: the default dataclass repr would print api_hash in the
        clear via %r, an f-string {!r}, or list repr (e.g. logging a batch
        of results) — __str__ alone doesn't protect against those paths.
        """
        r = ConversionResult(source="/tdata", success=True, api_hash="s3cr3t_hash")
        assert "s3cr3t_hash" not in repr(r)
        assert "s3cr3t_hash" not in repr([r])

    def test_fingerprint_repr_does_not_leak_api_hash(self):
        fp = TDataFingerprint(
            api_id=1, api_hash="s3cr3t_hash",
            device_model="d", system_version="s", app_version="a",
        )
        assert "s3cr3t_hash" not in repr(fp)
        assert "s3cr3t_hash" not in repr([fp])
