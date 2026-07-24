"""
tests/test_proxy_checker_country.py — country field wiring in
src/proxy/proxy_checker.py::check_proxy().

Focused on the new `country` field added to ProxyState; the connector
protocols themselves (SOCKS4/5, HTTP CONNECT) aren't covered by a dedicated
test file in this codebase, so this mocks the connector dispatch table
directly rather than opening real sockets.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.proxy.proxy_checker import ProxyType, check_proxy

pytestmark = pytest.mark.unit


def _fake_connector(*, raises=None):
    async def _connect(host, port, target_host, target_port, username, password, timeout):
        if raises is not None:
            raise raises
        writer = MagicMock()
        writer.wait_closed = AsyncMock()
        return MagicMock(), writer
    return _connect


async def test_successful_check_carries_resolved_country():
    with (
        patch.dict("src.proxy.proxy_checker._CONNECTORS", {ProxyType.SOCKS5: _fake_connector()}),
        patch(
            "src.proxy.proxy_checker.country_for_proxy_host",
            new=AsyncMock(return_value="RU"),
        ),
    ):
        state = await check_proxy({"type": "socks5", "host": "1.2.3.4", "port": 1080})

    assert state.is_active is True
    assert state.country == "RU"


async def test_failed_check_still_carries_resolved_country():
    with (
        patch.dict(
            "src.proxy.proxy_checker._CONNECTORS",
            {ProxyType.SOCKS5: _fake_connector(raises=ConnectionError("refused"))},
        ),
        patch(
            "src.proxy.proxy_checker.country_for_proxy_host",
            new=AsyncMock(return_value="DE"),
        ),
    ):
        state = await check_proxy(
            {"type": "socks5", "host": "1.2.3.4", "port": 1080}, retries=0,
        )

    assert state.is_active is False
    assert state.country == "DE"


async def test_unresolvable_country_leaves_field_none():
    with (
        patch.dict("src.proxy.proxy_checker._CONNECTORS", {ProxyType.SOCKS5: _fake_connector()}),
        patch(
            "src.proxy.proxy_checker.country_for_proxy_host",
            new=AsyncMock(return_value=None),
        ),
    ):
        state = await check_proxy({"type": "socks5", "host": "1.2.3.4", "port": 1080})

    assert state.country is None


async def test_invalid_config_does_not_attempt_country_lookup():
    mock_country = AsyncMock(return_value="US")
    with patch("src.proxy.proxy_checker.country_for_proxy_host", new=mock_country):
        state = await check_proxy({"type": "socks5", "host": "", "port": 0})

    assert state.country is None
    mock_country.assert_not_awaited()
