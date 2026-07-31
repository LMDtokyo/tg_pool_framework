"""tests/test_license_client.py — LicenseServerClient.fetch_profile_names."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.licensing.client import LicenseServerClient, LicenseServerUnavailableError

pytestmark = pytest.mark.unit


def _fake_response(status_code: int, json_body: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body
    return response


async def test_fetch_profile_names_returns_the_server_pools():
    client = LicenseServerClient("http://license.invalid")
    response = _fake_response(200, {"first_names": ["Alex"], "last_names": ["Adams"]})

    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=response)):
        first_names, last_names = await client.fetch_profile_names()

    assert first_names == ["Alex"]
    assert last_names == ["Adams"]


async def test_fetch_profile_names_raises_on_non_200():
    client = LicenseServerClient("http://license.invalid")
    response = _fake_response(500, {})

    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=response)):
        with pytest.raises(LicenseServerUnavailableError):
            await client.fetch_profile_names()


async def test_fetch_profile_names_raises_on_empty_pools():
    client = LicenseServerClient("http://license.invalid")
    response = _fake_response(200, {"first_names": [], "last_names": []})

    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=response)):
        with pytest.raises(LicenseServerUnavailableError):
            await client.fetch_profile_names()


async def test_fetch_profile_names_raises_on_network_error():
    client = LicenseServerClient("http://license.invalid")

    with patch.object(
        httpx.AsyncClient, "get", AsyncMock(side_effect=httpx.ConnectError("refused"))
    ):
        with pytest.raises(LicenseServerUnavailableError):
            await client.fetch_profile_names()
