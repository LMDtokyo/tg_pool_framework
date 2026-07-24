"""
Proxy pool exit-IP checker.

Telegram Expert's proxy pool checker is different from a basic reachability
check: it sends real requests through proxies, records the public exit IP for
each request, and reports unique IPs, duplicates, and connection errors.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from src.proxy.proxy_checker import ProxyType, _CONNECTORS

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10.0
_DEFAULT_IP_SERVICE_HOST = "api.ipify.org"
_DEFAULT_IP_SERVICE_PATH = "/"
_IP_RE = re.compile(r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]{3,})")


@dataclass(frozen=True)
class ProxyPoolAttempt:
    index: int
    proxy_label: str
    exit_ip: Optional[str]
    latency_ms: float
    error_message: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.exit_ip is not None and self.error_message is None


@dataclass(frozen=True)
class ProxyPoolReport:
    mode: str
    protocol: str
    total: int
    unique_count: int
    duplicate_count: int
    error_count: int
    attempts: List[ProxyPoolAttempt]


ExitIpFetcher = Callable[[Dict[str, Any], int], Awaitable[ProxyPoolAttempt]]


def proxy_label(proxy_config: Dict[str, Any]) -> str:
    return f"{proxy_config.get('host', '')}:{proxy_config.get('port', '')}"


def _parse_proxy_type(proxy_config: Dict[str, Any]) -> ProxyType:
    raw_type = str(proxy_config.get("type", "http")).lower().replace(" ", "")
    if raw_type == "socks":
        raw_type = "socks5"
    return ProxyType(raw_type)


def _extract_ip(text: str) -> str:
    match = _IP_RE.search(text.strip())
    if not match:
        raise ValueError(f"IP service returned no IP address: {text[:80]!r}")

    ip = match.group("ip")
    ipaddress.ip_address(ip)
    return ip


async def fetch_exit_ip(
    proxy_config: Dict[str, Any],
    index: int,
    *,
    target_host: str = _DEFAULT_IP_SERVICE_HOST,
    target_path: str = _DEFAULT_IP_SERVICE_PATH,
) -> ProxyPoolAttempt:
    """Fetch the public IP seen by an HTTP IP service through one proxy."""
    proxy_type = _parse_proxy_type(proxy_config)
    host = str(proxy_config.get("host", "")).strip()
    port = int(proxy_config.get("port", 0))
    username = proxy_config.get("username") or None
    password = proxy_config.get("password") or None
    timeout = float(proxy_config.get("timeout", _DEFAULT_TIMEOUT))
    label = proxy_label(proxy_config)
    t0 = time.monotonic()
    writer = None

    if not host or not port:
        return ProxyPoolAttempt(index, label, None, 0.0, "Proxy host and port are required")

    try:
        connector = _CONNECTORS[proxy_type]
        reader, writer = await connector(
            host, port, target_host, 80, username, password, timeout
        )
        request = (
            f"GET {target_path} HTTP/1.1\r\n"
            f"Host: {target_host}\r\n"
            "User-Agent: tg-pool-framework/1.0\r\n"
            "Accept: text/plain\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(request.encode("ascii"))
        await writer.drain()

        payload = await asyncio.wait_for(reader.read(65536), timeout=timeout)
        latency_ms = (time.monotonic() - t0) * 1000.0
        if not payload:
            raise ConnectionError("IP service returned an empty response")

        _headers, sep, body = payload.partition(b"\r\n\r\n")
        if not sep:
            body = payload
        exit_ip = _extract_ip(body.decode("utf-8", errors="replace"))
        return ProxyPoolAttempt(index, label, exit_ip, latency_ms)
    except asyncio.TimeoutError:
        latency_ms = (time.monotonic() - t0) * 1000.0
        return ProxyPoolAttempt(index, label, None, latency_ms, f"Timed out after {timeout:.1f}s")
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000.0
        logger.warning("Proxy pool attempt failed for %s: %s", label, exc)
        return ProxyPoolAttempt(index, label, None, latency_ms, str(exc))
    finally:
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


async def check_proxy_pool(
    proxies: Iterable[Dict[str, Any]],
    *,
    mode: str,
    request_count: Optional[int] = None,
    concurrency: int = 10,
    fetcher: Optional[ExitIpFetcher] = None,
) -> ProxyPoolReport:
    """
    Run a proxy pool check.

    Rotating mode expects one proxy config and repeats it request_count times.
    Sticky mode expects a list and checks each proxy once.
    """
    proxy_list = list(proxies)
    normalized_mode = mode.lower().strip()
    if normalized_mode not in {"rotating", "sticky"}:
        raise ValueError("mode must be 'rotating' or 'sticky'")

    if normalized_mode == "rotating":
        if not proxy_list:
            raise ValueError("Rotating mode requires one proxy")
        total = int(request_count or 0)
        if total <= 0:
            raise ValueError("Number of requests must be greater than 0")
        work_items = [proxy_list[0] for _ in range(total)]
    else:
        if not proxy_list:
            raise ValueError("Sticky mode requires at least one proxy")
        work_items = proxy_list

    protocol = str(work_items[0].get("type", "http")).lower()
    attempt_fetcher = fetcher or fetch_exit_ip
    queue: asyncio.Queue[tuple[int, Dict[str, Any]]] = asyncio.Queue()
    for index, proxy in enumerate(work_items, start=1):
        queue.put_nowait((index, proxy))

    attempts_by_index: dict[int, ProxyPoolAttempt] = {}

    async def _worker() -> None:
        while True:
            try:
                index, proxy_config = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                attempts_by_index[index] = await attempt_fetcher(proxy_config, index)
            finally:
                queue.task_done()

    worker_count = min(max(concurrency, 1), len(work_items))
    await asyncio.gather(*(_worker() for _ in range(worker_count)))
    attempts = [attempts_by_index[index] for index in sorted(attempts_by_index)]
    successful_ips = [attempt.exit_ip for attempt in attempts if attempt.exit_ip]
    unique_ips = set(successful_ips)
    error_count = sum(1 for attempt in attempts if not attempt.is_success)

    return ProxyPoolReport(
        mode=normalized_mode,
        protocol=protocol,
        total=len(work_items),
        unique_count=len(unique_ips),
        duplicate_count=max(len(successful_ips) - len(unique_ips), 0),
        error_count=error_count,
        attempts=attempts,
    )
