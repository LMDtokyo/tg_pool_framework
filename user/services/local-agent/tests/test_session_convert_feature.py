"""tests/test_session_convert_feature.py — tg_pool/features/session_convert.py (MODE=convert_session)."""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from tg_pool.features import session_convert
from tg_pool.proxy.tdata_converter import ConversionResult

pytestmark = pytest.mark.unit


def _make_session_pair(root, stem="acc1"):
    (root / f"{stem}.session").write_bytes(b"\x00")
    (root / f"{stem}.json").write_text('{"app_id": 1, "app_hash": "h"}', encoding="utf-8")


async def test_missing_env_var_logs_error(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    monkeypatch.delenv("SESSION_CONVERT_DIR", raising=False)

    await session_convert.run(None, logging.getLogger("test"))

    assert any("SESSION_CONVERT_DIR" in r.message for r in caplog.records)


async def test_nonexistent_dir_logs_error(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.ERROR)
    monkeypatch.setenv("SESSION_CONVERT_DIR", str(tmp_path / "does_not_exist"))

    await session_convert.run(None, logging.getLogger("test"))

    assert any("SESSION_CONVERT_DIR" in r.message for r in caplog.records)


async def test_no_session_pairs_logs_warning(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("SESSION_CONVERT_DIR", str(tmp_path))

    await session_convert.run(None, logging.getLogger("test"))

    assert any("не найдены" in r.message for r in caplog.records)


async def test_session_without_json_pair_is_skipped(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.WARNING)
    (tmp_path / "orphan.session").write_bytes(b"\x00")
    monkeypatch.setenv("SESSION_CONVERT_DIR", str(tmp_path))

    await session_convert.run(None, logging.getLogger("test"))

    assert any("orphan.session" in r.message for r in caplog.records)


async def test_converts_found_pairs_and_reports(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.INFO)
    _make_session_pair(tmp_path)
    monkeypatch.setenv("SESSION_CONVERT_DIR", str(tmp_path))
    monkeypatch.setenv("SESSION_CONVERT_OUTPUT_DIR", str(tmp_path / "out"))

    results = [ConversionResult(source=str(tmp_path / "acc1.session"), output="out/acc1", success=True)]
    mock_convert = AsyncMock(return_value=results)

    with patch.object(session_convert.TDataConverter, "convert_batch_sessions", mock_convert):
        await session_convert.run(None, logging.getLogger("test"))

    mock_convert.assert_awaited_once()
    args, kwargs = mock_convert.call_args
    assert args[0] == [(str(tmp_path / "acc1.session"), str(tmp_path / "acc1.json"), "acc1")]
    assert args[1] == str(tmp_path / "out")
    assert any("Готово: 1/1" in r.message for r in caplog.records)


async def test_failed_conversion_logged_as_error(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.ERROR)
    _make_session_pair(tmp_path)
    monkeypatch.setenv("SESSION_CONVERT_DIR", str(tmp_path))

    results = [ConversionResult(source="bad", output=None, success=False, error="not authorised")]
    mock_convert = AsyncMock(return_value=results)

    with patch.object(session_convert.TDataConverter, "convert_batch_sessions", mock_convert):
        await session_convert.run(None, logging.getLogger("test"))

    assert any("not authorised" in r.message for r in caplog.records)
