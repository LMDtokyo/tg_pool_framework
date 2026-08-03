"""tests/test_proxy_geo.py — Tests for tg_pool/proxy/proxy_geo.py.

geoip2fast bundles its own database, so these hit the real lookup
(no network call, no mocking needed) -- same reasoning as
tests/test_tdata_converter.py exercising the real conversion path.
"""

from __future__ import annotations

import pytest

from tg_pool.proxy.proxy_geo import country_for_proxy_host

pytestmark = pytest.mark.unit


async def test_known_public_ip_resolves_country():
    assert await country_for_proxy_host("8.8.8.8") == "US"


async def test_private_ip_returns_none():
    assert await country_for_proxy_host("192.168.1.1") is None


async def test_invalid_host_returns_none():
    assert await country_for_proxy_host("not-a-real-hostname.invalid") is None


async def test_empty_host_returns_none():
    assert await country_for_proxy_host("") is None
