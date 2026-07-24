"""tests/test_proxy_list.py — JSON proxy-list loader for standalone proxy checking."""

import json

import pytest

from src.proxy.proxy_list import load_proxies_from_json

pytestmark = pytest.mark.unit


def test_loads_valid_list(tmp_path):
    path = tmp_path / "proxies.json"
    path.write_text(json.dumps([
        {"type": "socks5", "host": "1.2.3.4", "port": 1080},
        {"type": "http", "host": "5.6.7.8", "port": 8080, "username": "u", "password": "p"},
    ]), encoding="utf-8")

    proxies = load_proxies_from_json(str(path))

    assert len(proxies) == 2
    assert proxies[0]["host"] == "1.2.3.4"
    assert proxies[1]["username"] == "u"


def test_not_a_list_raises(tmp_path):
    path = tmp_path / "proxies.json"
    path.write_text(json.dumps({"host": "1.2.3.4"}), encoding="utf-8")

    with pytest.raises(ValueError, match="expected a JSON array"):
        load_proxies_from_json(str(path))


def test_entry_not_an_object_raises_with_index(tmp_path):
    path = tmp_path / "proxies.json"
    path.write_text(json.dumps(["not-an-object"]), encoding="utf-8")

    with pytest.raises(ValueError, match=r"\[0\]"):
        load_proxies_from_json(str(path))


def test_missing_host_raises_with_index(tmp_path):
    path = tmp_path / "proxies.json"
    path.write_text(json.dumps([{"port": 1080}]), encoding="utf-8")

    with pytest.raises(ValueError, match=r"\[0\].*host"):
        load_proxies_from_json(str(path))


def test_missing_port_raises_with_index(tmp_path):
    path = tmp_path / "proxies.json"
    path.write_text(json.dumps([{"host": "1.2.3.4"}]), encoding="utf-8")

    with pytest.raises(ValueError, match=r"\[0\].*port"):
        load_proxies_from_json(str(path))


def test_empty_list_returns_empty(tmp_path):
    path = tmp_path / "proxies.json"
    path.write_text("[]", encoding="utf-8")

    assert load_proxies_from_json(str(path)) == []


def test_malformed_json_raises(tmp_path):
    path = tmp_path / "proxies.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_proxies_from_json(str(path))
