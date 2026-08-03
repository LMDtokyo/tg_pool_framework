"""Parsing for the proxy-list text accepted by the desktop client."""

from __future__ import annotations

from typing import Any, Dict, List


SUPPORTED_PROXY_TYPES = {"http", "socks5"}


def parse_proxy_lines(text: str, proxy_type: str) -> List[Dict[str, Any]]:
    """Parse ``host:port`` or ``host:port:login:password`` lines."""
    normalized_type = proxy_type.strip().lower()
    if normalized_type not in SUPPORTED_PROXY_TYPES:
        raise ValueError("Proxy type must be 'http' or 'socks5'.")

    proxies: List[Dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    errors: List[str] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = [part.strip() for part in line.split(":")]
        if len(parts) not in (2, 4):
            errors.append(
                f"line {line_number}: expected host:port or host:port:login:password"
            )
            continue

        host = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            port = 0
        username = parts[2] if len(parts) == 4 else ""
        password = parts[3] if len(parts) == 4 else ""

        if not host:
            errors.append(f"line {line_number}: host is empty")
        elif not 1 <= port <= 65535:
            errors.append(f"line {line_number}: port must be between 1 and 65535")
        elif len(parts) == 4 and (not username or not password):
            errors.append(f"line {line_number}: login and password must both be provided")
        else:
            key = (host.lower(), port, username)
            if key not in seen:
                seen.add(key)
                proxies.append(
                    {
                        "proxy_type": normalized_type,
                        "host": host,
                        "port": port,
                        "username": username,
                        "password": password,
                    }
                )

    if errors:
        preview = "; ".join(errors[:5])
        if len(errors) > 5:
            preview += f"; and {len(errors) - 5} more"
        raise ValueError(preview)
    if not proxies:
        raise ValueError("The proxy list is empty.")
    return proxies
