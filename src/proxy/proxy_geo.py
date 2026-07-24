"""
src/proxy/proxy_geo.py — Offline country lookup for proxy hosts.

Uses geoip2fast (bundles its own database -- no MaxMind account, API key,
or network call needed) to resolve a proxy's host to a 2-letter country
code, so proxies can be picked to match a target audience's geography.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 5.0

_geoip = None


def _get_geoip():
    """Lazily builds the singleton GeoIP2Fast instance (~50ms to load its bundled db)."""
    global _geoip
    if _geoip is None:
        import geoip2fast
        _geoip = geoip2fast.GeoIP2Fast()
    return _geoip


async def _resolve_to_ip(host: str, timeout: float) -> str:
    """Returns host unchanged if it's already an IP literal, otherwise resolves via DNS."""
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    infos = await asyncio.wait_for(
        loop.getaddrinfo(host, None, type=socket.SOCK_STREAM),
        timeout=timeout,
    )
    return infos[0][4][0]


async def country_for_proxy_host(host: str, *, timeout: float = _DEFAULT_TIMEOUT) -> Optional[str]:
    """
    Returns the 2-letter ISO country code for a proxy host, or None if it
    can't be determined (DNS failure, private/reserved IP, lookup miss).
    Never raises -- a bad geo lookup can't be allowed to derail a proxy check.
    """
    try:
        ip = await _resolve_to_ip(host, timeout)
        code = _get_geoip().lookup(ip).country_code
        return code if code and code != "--" else None
    except Exception:
        logger.warning("country_for_proxy_host(%s) failed", host, exc_info=True)
        return None
