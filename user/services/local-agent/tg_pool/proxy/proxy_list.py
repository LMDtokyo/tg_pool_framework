"""
tg_pool/proxy/proxy_list.py — JSON proxy-list loader for standalone proxy checking.

Format: a JSON array of proxy dicts, matching check_proxy()'s own config
contract 1:1 -- no adapter needed between the file format and the checker.

    [
      {"type": "socks5", "host": "1.2.3.4", "port": 1080, "username": "...", "password": "..."},
      {"type": "http", "host": "5.6.7.8", "port": 8080}
    ]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

_REQUIRED_FIELDS = ("host", "port")


def load_proxies_from_json(path: str) -> List[Dict[str, Any]]:
    """
    Reads a JSON array of proxy configs (see module docstring for format).

    Raises ValueError naming the offending index/field for a malformed file
    (missing host/port, not a list, not an object) instead of failing deep
    inside check_proxy() with no indication of which entry was broken.
    """
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)

    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array of proxy objects, got {type(data).__name__}")

    proxies: List[Dict[str, Any]] = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}[{i}]: expected an object, got {type(entry).__name__}")
        missing = [f for f in _REQUIRED_FIELDS if not entry.get(f)]
        if missing:
            raise ValueError(f"{path}[{i}]: missing required field(s) {missing}")
        proxies.append(entry)

    return proxies
