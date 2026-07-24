"""tests/test_proxy_check_feature.py — src/features/proxy_check.py (MODE=check_proxies)."""

import json
import logging

import pytest

from src.features import proxy_check
from src.proxy.proxy_checker import ProxyState, ProxyType

pytestmark = pytest.mark.unit


def _write_proxy_list(tmp_path, proxies):
    path = tmp_path / "proxies.json"
    path.write_text(json.dumps(proxies), encoding="utf-8")
    return str(path)


async def test_missing_env_var_logs_error_and_returns(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    monkeypatch.delenv("PROXY_LIST_JSON", raising=False)

    await proxy_check.run(None, logging.getLogger("test"))

    assert any("PROXY_LIST_JSON" in r.message for r in caplog.records)


async def test_bad_json_file_logs_error_and_returns(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.ERROR)
    path = tmp_path / "bad.json"
    path.write_text("{not valid", encoding="utf-8")
    monkeypatch.setenv("PROXY_LIST_JSON", str(path))

    await proxy_check.run(None, logging.getLogger("test"))

    assert any(str(path) in r.message for r in caplog.records)


async def test_empty_list_logs_warning(monkeypatch, caplog, tmp_path):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("PROXY_LIST_JSON", _write_proxy_list(tmp_path, []))

    await proxy_check.run(None, logging.getLogger("test"))

    assert any("пуст" in r.message for r in caplog.records)


async def test_checks_all_proxies_and_writes_report(monkeypatch, tmp_path):
    list_path = _write_proxy_list(tmp_path, [
        {"type": "socks5", "host": "1.2.3.4", "port": 1080},
        {"type": "http", "host": "5.6.7.8", "port": 8080},
    ])
    monkeypatch.setenv("PROXY_LIST_JSON", list_path)
    report_path = tmp_path / "report.json"
    monkeypatch.setenv("PROXY_CHECK_REPORT_PATH", str(report_path))

    async def fake_check_all(proxies, *, concurrency=10):
        return [
            ProxyState(is_active=True, latency_ms=42.0, proxy_type=ProxyType.SOCKS5),
            ProxyState(is_active=False, latency_ms=0.0, proxy_type=ProxyType.HTTP, error_message="dead"),
        ]

    monkeypatch.setattr(proxy_check, "check_all_proxies", fake_check_all)

    await proxy_check.run(None, logging.getLogger("test"))

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(report) == 2
    assert report[0]["is_active"] is True
    assert report[0]["latency_ms"] == 42.0
    assert report[1]["is_active"] is False
    assert report[1]["error"] == "dead"


async def test_no_report_path_skips_file_write(monkeypatch, tmp_path):
    list_path = _write_proxy_list(tmp_path, [{"type": "socks5", "host": "1.2.3.4", "port": 1080}])
    monkeypatch.setenv("PROXY_LIST_JSON", list_path)
    monkeypatch.delenv("PROXY_CHECK_REPORT_PATH", raising=False)

    async def fake_check_all(proxies, *, concurrency=10):
        return [ProxyState(is_active=True, latency_ms=1.0, proxy_type=ProxyType.SOCKS5)]

    monkeypatch.setattr(proxy_check, "check_all_proxies", fake_check_all)

    await proxy_check.run(None, logging.getLogger("test"))  # must not raise
