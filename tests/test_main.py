"""tests/test_main.py — main.py's mode dispatcher (choose_mode + main())."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

import main

pytestmark = pytest.mark.unit


class TestChooseMode:
    def test_mode_env_var_returned_directly(self, monkeypatch):
        monkeypatch.setenv("MODE", "send")
        assert main.choose_mode(logging.getLogger("test")) == "send"

    def test_mode_env_var_lowercased_and_stripped(self, monkeypatch):
        monkeypatch.setenv("MODE", "  SEND  ")
        assert main.choose_mode(logging.getLogger("test")) == "send"

    def test_no_mode_no_tty_logs_error_and_returns_none(self, monkeypatch, caplog):
        caplog.set_level(logging.ERROR)
        monkeypatch.delenv("MODE", raising=False)

        with patch("sys.stdin.isatty", return_value=False):
            result = main.choose_mode(logging.getLogger("test"))

        assert result is None
        assert any("MODE" in r.message for r in caplog.records)

    def test_no_mode_tty_prompts_and_returns_choice(self, monkeypatch):
        monkeypatch.delenv("MODE", raising=False)

        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("rich.prompt.Prompt.ask", return_value="check_proxies") as mock_ask,
        ):
            result = main.choose_mode(logging.getLogger("test"))

        assert result == "check_proxies"
        mock_ask.assert_called_once()


class TestMainDispatch:
    async def test_unknown_mode_exits_nonzero(self, monkeypatch):
        monkeypatch.setenv("MODE", "not_a_real_mode")

        with pytest.raises(SystemExit) as exc_info:
            await main.main()

        assert exc_info.value.code == 1

    async def test_no_mode_no_tty_exits_nonzero(self, monkeypatch):
        monkeypatch.delenv("MODE", raising=False)

        with patch("sys.stdin.isatty", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                await main.main()

        assert exc_info.value.code == 1

    async def test_dispatches_to_the_right_feature_module(self, monkeypatch):
        monkeypatch.setenv("MODE", "check_proxies")
        mock_run = AsyncMock()

        with patch("src.features.proxy_check.run", mock_run):
            await main.main()

        mock_run.assert_awaited_once()
        args = mock_run.call_args[0]
        assert isinstance(args[0], asyncio.Event)
        assert isinstance(args[1], logging.Logger)

    async def test_dispatches_send_mode_to_messaging_module(self, monkeypatch):
        monkeypatch.setenv("MODE", "send")
        mock_run = AsyncMock()

        with patch("src.features.messaging.run", mock_run):
            await main.main()

        mock_run.assert_awaited_once()
