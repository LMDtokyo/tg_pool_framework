import asyncio
from unittest.mock import AsyncMock

import pytest

from src.api.stored_proxy_check import StoredProxyCheckManager
from src.db.engine import build_engine_and_session_factory
from src.db.proxy_repository import ProxyRepository, ensure_proxy_table
from src.proxy.proxy_checker import ProxyState, ProxyType


pytestmark = pytest.mark.unit


@pytest.fixture
async def repository():
    engine, session_factory = build_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    await ensure_proxy_table(session_factory)
    try:
        yield ProxyRepository(session_factory)
    finally:
        await engine.dispose()


def _proxy(password: str = "pass") -> dict:
    return {
        "proxy_type": "socks5",
        "host": "1.2.3.4",
        "port": 1080,
        "username": "user",
        "password": password,
    }


async def test_upsert_list_and_delete_proxy(repository):
    assert await repository.upsert_many([_proxy()]) == 1
    stored = await repository.list_all()

    assert len(stored) == 1
    assert stored[0].status == "unknown"
    assert stored[0].version == "ipv4"
    assert stored[0].checker_config(12)["timeout"] == 12

    assert await repository.delete_one(stored[0].id) is True
    assert await repository.list_all() == []


async def test_upsert_updates_credentials_without_creating_a_duplicate(repository):
    await repository.upsert_many([_proxy("old")])
    await repository.upsert_many([_proxy("new")])

    stored = await repository.list_all()
    assert len(stored) == 1
    assert stored[0].password == "new"


async def test_check_manager_persists_results_and_delete_bad(repository, monkeypatch):
    await repository.upsert_many([_proxy()])
    checked = ProxyState(
        is_active=False,
        latency_ms=123.5,
        proxy_type=ProxyType.SOCKS5,
        error_message="dead",
        country="DE",
    )
    mock_check = AsyncMock(return_value=[checked])
    monkeypatch.setattr("src.api.stored_proxy_check.check_all_proxies", mock_check)

    manager = StoredProxyCheckManager(repository)
    manager.start(None, concurrency=4, timeout=45, retries=15, retry_delay=0.25)
    while manager.is_running:
        await asyncio.sleep(0)

    stored = await repository.list_all()
    assert stored[0].status == "bad"
    assert stored[0].response_ms == 123.5
    assert stored[0].country == "DE"
    assert stored[0].last_checked_at is not None
    assert manager.status()["completed"] == 1
    assert mock_check.await_args.kwargs == {
        "concurrency": 4,
        "retries": 15,
        "retry_delay": 0.25,
    }
    assert mock_check.await_args.args[0][0]["timeout"] == 45

    assert await repository.delete_bad() == 1
    assert await repository.list_all() == []


async def test_delete_all_returns_number_of_removed_rows(repository):
    await repository.upsert_many(
        [
            _proxy(),
            _proxy() | {"host": "5.6.7.8", "username": ""},
        ]
    )

    assert await repository.delete_all() == 2


async def test_check_manager_stop_cancels_an_active_check(repository, monkeypatch):
    await repository.upsert_many([_proxy()])
    started = asyncio.Event()

    async def wait_forever(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("src.api.stored_proxy_check.check_all_proxies", wait_forever)
    manager = StoredProxyCheckManager(repository)
    manager.start(None, concurrency=1, timeout=10, retries=2, retry_delay=0.5)
    await started.wait()

    await manager.stop()

    assert manager.is_running is False
