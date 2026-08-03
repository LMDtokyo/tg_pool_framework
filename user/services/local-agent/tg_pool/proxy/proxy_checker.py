"""
tg_pool/proxy_checker.py — Async proxy health checker.

Tests proxy servers by establishing a TCP tunnel through them to a Telegram DC
and measuring round-trip latency.  No Telethon or TLS handshake is performed —
only the proxy tunnel layer is verified.

Supported proxy types: HTTP, HTTPS, SOCKS4, SOCKS5.

Protocol implementations are pure asyncio (no blocking calls, no extra deps):
  SOCKS5 — RFC 1928 handshake with optional username/password auth (RFC 1929).
  SOCKS4 — VN=4, CMD=1 connect request.
  HTTP/HTTPS — HTTP CONNECT tunnel with optional Proxy-Authorization header.

Usage:
    from tg_pool.proxy.proxy_checker import check_proxy, ProxyType, ProxyState

    state = await check_proxy({
        "type": "socks5",
        "host": "proxy.example.com",
        "port": 1080,
        "username": "user",    # optional
        "password": "pass",    # optional
        "timeout": 10.0,       # optional, seconds
    })
    if state.is_active:
        print(f"Latency: {state.latency_ms:.1f} ms")
    else:
        print(f"Dead: {state.error_message}")
"""

from __future__ import annotations

import asyncio
import base64
import logging
import socket
import time
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from tg_pool.proxy.proxy_geo import country_for_proxy_host

logger = logging.getLogger(__name__)

# Telegram DC2 — stable, reachable globally, ideal for latency probing
_TG_TEST_HOST = "149.154.167.50"
_TG_TEST_PORT = 443
_DEFAULT_TIMEOUT = 10.0

# SOCKS5 reply codes
_SOCKS5_SUCCESS = 0x00

# SOCKS4 reply codes
_SOCKS4_GRANTED = 0x5A

# HTTP CONNECT success marker
_HTTP_CONNECT_OK = b"200"


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class ProxyType(str, Enum):
    HTTP   = "http"
    HTTPS  = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


@dataclass(frozen=True)
class ProxyState:
    """Immutable result of a single proxy check."""
    is_active: bool
    latency_ms: float
    proxy_type: ProxyType
    error_message: Optional[str] = None
    country: Optional[str] = None


# ---------------------------------------------------------------------------
# Protocol implementations
# ---------------------------------------------------------------------------

async def _connect_via_socks5(
    host: str,
    port: int,
    target_host: str,
    target_port: int,
    username: Optional[str],
    password: Optional[str],
    timeout: float,
) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Establish a SOCKS5 tunnel to target_host:target_port via host:port."""
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port),
        timeout=timeout,
    )

    # --- Auth method negotiation ---
    methods = bytearray([0x00])  # NO AUTH
    if username and password:
        methods.append(0x02)     # USERNAME/PASSWORD
    writer.write(bytes([0x05, len(methods)]) + bytes(methods))
    await writer.drain()

    greeting = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
    if greeting[0] != 0x05:
        writer.close()
        raise ConnectionError("Server returned non-SOCKS5 greeting")

    chosen = greeting[1]
    if chosen == 0xFF:
        writer.close()
        raise ConnectionError("SOCKS5: no acceptable auth method")

    # --- Username/password auth (RFC 1929) ---
    if chosen == 0x02:
        uname = (username or "").encode()
        passwd = (password or "").encode()
        writer.write(
            bytes([0x01, len(uname)]) + uname + bytes([len(passwd)]) + passwd
        )
        await writer.drain()
        auth_resp = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
        if auth_resp[1] != 0x00:
            writer.close()
            raise ConnectionError("SOCKS5: authentication failed")

    # --- CONNECT request (ATYP=0x03 domain name) ---
    target_bytes = target_host.encode()
    writer.write(
        bytes([0x05, 0x01, 0x00, 0x03, len(target_bytes)])
        + target_bytes
        + target_port.to_bytes(2, "big")
    )
    await writer.drain()

    # --- Parse response (handle IPv4 / IPv6 / domain ATYP) ---
    header = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
    if header[1] != _SOCKS5_SUCCESS:
        writer.close()
        raise ConnectionError(f"SOCKS5 CONNECT failed: reply code {header[1]:#04x}")

    atyp = header[3]
    if atyp == 0x01:                                        # IPv4: 4 + 2
        await asyncio.wait_for(reader.readexactly(6), timeout=timeout)
    elif atyp == 0x03:                                      # Domain: 1+N + 2
        dom_len = (await asyncio.wait_for(reader.readexactly(1), timeout=timeout))[0]
        await asyncio.wait_for(reader.readexactly(dom_len + 2), timeout=timeout)
    elif atyp == 0x04:                                      # IPv6: 16 + 2
        await asyncio.wait_for(reader.readexactly(18), timeout=timeout)

    return reader, writer


async def _connect_via_socks4(
    host: str,
    port: int,
    target_host: str,
    target_port: int,
    username: Optional[str],
    _password: Optional[str],  # SOCKS4 has no password field
    timeout: float,
) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Establish a SOCKS4 tunnel (no auth negotiation; user ID only)."""
    # SOCKS4 requires IPv4 address — resolve the target domain first.
    # Wrapped in the same timeout as the connection itself: an unresponsive
    # resolver must not be able to stall past the caller's declared timeout.
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(
                target_host, None,
                family=socket.AF_INET,
                type=socket.SOCK_STREAM,
            ),
            timeout=timeout,
        )
        target_ip = infos[0][4][0]
    except asyncio.TimeoutError:
        raise
    except Exception as exc:
        raise ConnectionError(f"SOCKS4: cannot resolve '{target_host}': {exc}") from exc

    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port),
        timeout=timeout,
    )

    ip_bytes = socket.inet_aton(target_ip)
    user_bytes = (username or "").encode() + b"\x00"

    writer.write(
        bytes([0x04, 0x01])
        + target_port.to_bytes(2, "big")
        + ip_bytes
        + user_bytes
    )
    await writer.drain()

    resp = await asyncio.wait_for(reader.readexactly(8), timeout=timeout)
    if resp[1] != _SOCKS4_GRANTED:
        writer.close()
        raise ConnectionError(f"SOCKS4 rejected: code {resp[1]:#04x}")

    return reader, writer


async def _connect_via_http(
    host: str,
    port: int,
    target_host: str,
    target_port: int,
    username: Optional[str],
    password: Optional[str],
    timeout: float,
    use_tls: bool = False,
) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """HTTP CONNECT tunnel (also used for HTTPS proxy)."""
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=use_tls),
        timeout=timeout,
    )

    connect_line = (
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n"
    )
    if username and password:
        creds = base64.b64encode(f"{username}:{password}".encode()).decode()
        connect_line += f"Proxy-Authorization: Basic {creds}\r\n"
    connect_line += "\r\n"

    writer.write(connect_line.encode())
    await writer.drain()

    # Read until end of HTTP response headers
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = await asyncio.wait_for(reader.read(1024), timeout=timeout)
        if not chunk:
            break
        response += chunk
        if len(response) > 8192:
            break  # guard against runaway proxy

    if _HTTP_CONNECT_OK not in response:
        writer.close()
        raise ConnectionError(
            f"HTTP CONNECT failed: {response[:100]!r}"
        )

    return reader, writer


# Dispatch table: ProxyType → connector coroutine
_CONNECTORS = {
    ProxyType.SOCKS5: _connect_via_socks5,
    ProxyType.SOCKS4: _connect_via_socks4,
    ProxyType.HTTP:   lambda h, p, th, tp, u, pw, t: _connect_via_http(
        h, p, th, tp, u, pw, t, use_tls=False
    ),
    ProxyType.HTTPS:  lambda h, p, th, tp, u, pw, t: _connect_via_http(
        h, p, th, tp, u, pw, t, use_tls=True
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def _attempt_connect(
    proxy_type: ProxyType,
    host: str,
    port: int,
    username: Optional[str],
    password: Optional[str],
    timeout: float,
    target_host: str,
    target_port: int,
) -> ProxyState:
    """One connection attempt. Never raises — failures become ProxyState(is_active=False)."""
    connector = _CONNECTORS[proxy_type]
    t0 = time.monotonic()
    writer: Optional[asyncio.StreamWriter] = None

    try:
        _, writer = await connector(
            host, port, target_host, target_port, username, password, timeout
        )
        latency_ms = (time.monotonic() - t0) * 1000.0

        logger.info(
            "Proxy %s:%d (%s) → %s:%d  latency=%.1fms",
            host, port, proxy_type.value, target_host, target_port, latency_ms,
        )
        return ProxyState(
            is_active=True,
            latency_ms=latency_ms,
            proxy_type=proxy_type,
        )

    except asyncio.TimeoutError:
        latency_ms = (time.monotonic() - t0) * 1000.0
        msg = f"Timed out after {timeout:.1f}s connecting {host}:{port}"
        logger.warning("Proxy DEAD (timeout): %s", msg)
        return ProxyState(
            is_active=False,
            latency_ms=latency_ms,
            proxy_type=proxy_type,
            error_message=msg,
        )

    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000.0
        msg = str(exc)
        logger.warning("Proxy DEAD (%s:%d): %s", host, port, msg)
        return ProxyState(
            is_active=False,
            latency_ms=latency_ms,
            proxy_type=proxy_type,
            error_message=msg,
        )

    finally:
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


async def check_proxy(
    proxy_config: dict,
    *,
    target_host: str = _TG_TEST_HOST,
    target_port: int = _TG_TEST_PORT,
    retries: int = 2,
    retry_delay: float = 0.5,
) -> ProxyState:
    """
    Test a proxy by establishing a TCP tunnel to a Telegram DC.

    Args:
      proxy_config — dict with keys:
        type     (str)   — "http" | "https" | "socks4" | "socks5"
        host     (str)   — proxy host
        port     (int)   — proxy port
        username (str)   — optional credentials
        password (str)   — optional credentials
        timeout  (float) — connection timeout in seconds (default 10.0)
      target_host  — Telegram DC host to connect through proxy (override for tests)
      target_port  — Telegram DC port (override for tests)
      retries      — extra attempts after the first on failure (default 2, so up
                     to 3 total) — a single dropped SYN or slow DNS response
                     shouldn't be indistinguishable from a genuinely dead proxy.
      retry_delay  — pause between attempts, seconds.

    Returns a ProxyState with is_active, latency_ms, proxy_type, error_message
    (the result of the LAST attempt). Never raises — all errors are captured
    in ProxyState.error_message. A config error (bad type/missing host/port)
    is not retried — retrying won't fix a malformed config.
    """
    raw_type = str(proxy_config.get("type", "socks5")).lower()
    try:
        proxy_type = ProxyType(raw_type)
    except ValueError:
        return ProxyState(
            is_active=False,
            latency_ms=0.0,
            proxy_type=ProxyType.SOCKS5,
            error_message=f"Unknown proxy type: {raw_type!r}",
        )

    host = str(proxy_config.get("host", ""))
    port = int(proxy_config.get("port", 0))
    username: Optional[str] = proxy_config.get("username") or None
    password: Optional[str] = proxy_config.get("password") or None
    timeout = float(proxy_config.get("timeout", _DEFAULT_TIMEOUT))

    if not host or not port:
        return ProxyState(
            is_active=False,
            latency_ms=0.0,
            proxy_type=proxy_type,
            error_message="proxy_config must contain non-empty 'host' and 'port'",
        )

    country = await country_for_proxy_host(host)

    attempts = max(retries, 0) + 1
    state: ProxyState
    for attempt in range(1, attempts + 1):
        state = await _attempt_connect(
            proxy_type, host, port, username, password, timeout, target_host, target_port,
        )
        if state.is_active or attempt == attempts:
            return replace(state, country=country)
        logger.info(
            "Proxy %s:%d attempt %d/%d failed (%s) — retrying.",
            host, port, attempt, attempts, state.error_message,
        )
        await asyncio.sleep(retry_delay)
    return replace(state, country=country)


async def check_all_proxies(
    proxies: List[Dict[str, Any]],
    *,
    concurrency: int = 10,
    **check_proxy_kwargs: Any,
) -> List[ProxyState]:
    """
    Checks a batch of proxy configs concurrently, bounded by `concurrency`
    (same semaphore-fan-out pattern as HealthChecker.check_pool_health()).

    Returns one ProxyState per input proxy, in the same order -- never raises,
    since check_proxy() itself never raises.
    """
    sem = asyncio.Semaphore(max(concurrency, 1))

    async def _bounded(proxy_config: Dict[str, Any]) -> ProxyState:
        async with sem:
            return await check_proxy(proxy_config, **check_proxy_kwargs)

    return list(await asyncio.gather(*(_bounded(p) for p in proxies)))


async def check_account_proxies(
    accounts: List[Any],
    *,
    concurrency: int = 10,
    **check_proxy_kwargs: Any,
) -> Dict[str, ProxyState]:
    """
    Checks the proxy attached to each account (tg_pool.config.AccountConfig) --
    accounts with no proxy are skipped, nothing to check. Used as an optional
    preflight gate before a campaign/parsing job, so a dead proxy is caught
    before Phase 0 burns time connecting through it.

    Returns {phone: ProxyState} for accounts that have a proxy attached.
    """
    with_proxy = [a for a in accounts if a.proxy is not None]
    if not with_proxy:
        return {}

    configs = [
        {
            "type": a.proxy.proxy_type,
            "host": a.proxy.host,
            "port": a.proxy.port,
            "username": a.proxy.username,
            "password": a.proxy.password,
        }
        for a in with_proxy
    ]
    results = await check_all_proxies(configs, concurrency=concurrency, **check_proxy_kwargs)
    return {a.phone: state for a, state in zip(with_proxy, results)}
