"""tests/test_tdata_convert_feature.py — src/features/tdata_convert.py (MODE=convert_tdata)."""

import json
import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.features import tdata_convert
from src.proxy.tdata_converter import ConversionResult

pytestmark = pytest.mark.unit


def _make_tdata_folder(root, name="acc1"):
    tdata_dir = root / name / "tdata"
    tdata_dir.mkdir(parents=True)
    (tdata_dir / "key_datas").write_bytes(b"\x00")
    return tdata_dir


async def test_missing_env_var_logs_error(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.ERROR)
    monkeypatch.delenv("TDATA_ACCOUNTS_DIR", raising=False)

    await tdata_convert.run(None, logging.getLogger("test"))

    assert any("TDATA_ACCOUNTS_DIR" in r.message for r in caplog.records)


async def test_nonexistent_dir_logs_error(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.ERROR)
    monkeypatch.setenv("TDATA_ACCOUNTS_DIR", str(tmp_path / "does_not_exist"))

    await tdata_convert.run(None, logging.getLogger("test"))

    assert any("TDATA_ACCOUNTS_DIR" in r.message for r in caplog.records)


async def test_no_tdata_folders_logs_warning(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("TDATA_ACCOUNTS_DIR", str(tmp_path))

    await tdata_convert.run(None, logging.getLogger("test"))

    assert any("не найдены" in r.message for r in caplog.records)


async def test_converts_found_folders_and_reports(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.INFO)
    tdata_dir = _make_tdata_folder(tmp_path)
    monkeypatch.setenv("TDATA_ACCOUNTS_DIR", str(tmp_path))
    monkeypatch.setenv("TDATA_OUTPUT_DIR", str(tmp_path / "sessions"))
    monkeypatch.delenv("TDATA_PASSWORDS_FILE", raising=False)
    monkeypatch.delenv("TDATA_ALL_ACCOUNTS", raising=False)

    results = [
        ConversionResult(source=str(tdata_dir.resolve()), output="sessions/79001234567.session", success=True),
    ]
    mock_convert = AsyncMock(return_value=results)

    with patch.object(tdata_convert.TDataConverter, "convert_batch_tdata", mock_convert):
        await tdata_convert.run(None, logging.getLogger("test"))

    mock_convert.assert_awaited_once()
    args, kwargs = mock_convert.call_args
    assert args[0] == [str(tdata_dir.resolve())]
    assert kwargs["all_accounts"] is False
    assert any("Готово: 1/1" in r.message for r in caplog.records)


async def test_all_accounts_flag_forwarded(monkeypatch, tmp_path):
    tdata_dir = _make_tdata_folder(tmp_path)
    monkeypatch.setenv("TDATA_ACCOUNTS_DIR", str(tmp_path))
    monkeypatch.setenv("TDATA_ALL_ACCOUNTS", "1")

    mock_convert = AsyncMock(return_value=[])
    with patch.object(tdata_convert.TDataConverter, "convert_batch_tdata", mock_convert):
        await tdata_convert.run(None, logging.getLogger("test"))

    assert mock_convert.call_args.kwargs["all_accounts"] is True


async def test_passwords_file_read_and_forwarded(monkeypatch, tmp_path):
    tdata_dir = _make_tdata_folder(tmp_path)
    resolved = str(tdata_dir.resolve())
    passwords_file = tmp_path / "passwords.json"
    passwords_file.write_text(json.dumps({resolved: "s3cr3t"}), encoding="utf-8")

    monkeypatch.setenv("TDATA_ACCOUNTS_DIR", str(tmp_path))
    monkeypatch.setenv("TDATA_PASSWORDS_FILE", str(passwords_file))

    mock_convert = AsyncMock(return_value=[])
    with patch.object(tdata_convert.TDataConverter, "convert_batch_tdata", mock_convert):
        await tdata_convert.run(None, logging.getLogger("test"))

    assert mock_convert.call_args.kwargs["passwords"] == {resolved: "s3cr3t"}


async def test_failed_conversion_logged_as_error(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.ERROR)
    _make_tdata_folder(tmp_path)
    monkeypatch.setenv("TDATA_ACCOUNTS_DIR", str(tmp_path))

    results = [ConversionResult(source="bad/path", output=None, success=False, error="invalid tdata")]
    mock_convert = AsyncMock(return_value=results)

    with patch.object(tdata_convert.TDataConverter, "convert_batch_tdata", mock_convert):
        await tdata_convert.run(None, logging.getLogger("test"))

    assert any("invalid tdata" in r.message for r in caplog.records)
