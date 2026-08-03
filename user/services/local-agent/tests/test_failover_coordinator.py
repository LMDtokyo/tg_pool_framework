"""
tests/test_failover_coordinator.py — FailoverCoordinator spare promotion + cleanup.

Regression coverage for the promoted-spare-client leak: get_replacement()
connects a fresh TelegramClient that ClientPool.close_all() never sees
(it's not in ClientPool._clients), so the coordinator must track and
disconnect its own promoted clients via close_promoted().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_pool.config import AccountConfig, TimingPolicy
from tg_pool.orchestrator import FailoverCoordinator

pytestmark = pytest.mark.unit

FAST_POLICY = TimingPolicy(
    base_delay_sec=0.0, jitter_sec=0.0,
    inter_message_delay_sec=0.0, inter_message_jitter_sec=0.0,
    startup_jitter_max_sec=0.0,
)


def make_spare(phone: str) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone)


def make_mock_client(authorized: bool = True) -> MagicMock:
    client = MagicMock()
    client.connect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=authorized)
    client.is_connected = MagicMock(return_value=True)
    client.disconnect = AsyncMock()
    return client


class TestGetReplacement:
    async def test_returns_connected_spare(self):
        spare = make_spare("+7002")
        coordinator = FailoverCoordinator([spare], FAST_POLICY)
        client = make_mock_client()

        with patch("tg_pool.orchestrator.ClientFactory.build", return_value=client):
            result = await coordinator.get_replacement("+7001")

        assert result == (client, "+7002")
        assert "+7001" in coordinator.dead_phones

    async def test_returns_none_when_no_spares(self):
        coordinator = FailoverCoordinator([], FAST_POLICY)
        result = await coordinator.get_replacement("+7001")
        assert result is None

    async def test_skips_unauthorized_spare_and_disconnects_it(self):
        spare = make_spare("+7002")
        coordinator = FailoverCoordinator([spare], FAST_POLICY)
        client = make_mock_client(authorized=False)

        with patch("tg_pool.orchestrator.ClientFactory.build", return_value=client):
            result = await coordinator.get_replacement("+7001")

        assert result is None
        client.disconnect.assert_awaited_once()

    async def test_skips_spare_that_fails_to_connect(self):
        good_spare = make_spare("+7003")
        bad_spare = make_spare("+7002")
        coordinator = FailoverCoordinator([bad_spare, good_spare], FAST_POLICY)

        bad_client = make_mock_client()
        bad_client.connect = AsyncMock(side_effect=ConnectionError("refused"))
        good_client = make_mock_client()

        with patch(
            "tg_pool.orchestrator.ClientFactory.build",
            side_effect=[bad_client, good_client],
        ):
            result = await coordinator.get_replacement("+7001")

        assert result == (good_client, "+7003")


class TestClosePromoted:
    async def test_disconnects_promoted_client_not_tracked_by_any_pool(self):
        """
        Regression: a promoted spare is never added to ClientPool._clients,
        so pool.close_all() can't see it — close_promoted() must disconnect
        it independently.
        """
        spare = make_spare("+7002")
        coordinator = FailoverCoordinator([spare], FAST_POLICY)
        client = make_mock_client()

        with patch("tg_pool.orchestrator.ClientFactory.build", return_value=client):
            await coordinator.get_replacement("+7001")

        client.disconnect.assert_not_awaited()

        await coordinator.close_promoted()

        client.disconnect.assert_awaited_once()

    async def test_close_promoted_is_a_noop_with_nothing_promoted(self):
        coordinator = FailoverCoordinator([], FAST_POLICY)
        await coordinator.close_promoted()  # must not raise

    async def test_close_promoted_disconnects_multiple_spares(self):
        spare_a, spare_b = make_spare("+7002"), make_spare("+7003")
        coordinator = FailoverCoordinator([spare_a, spare_b], FAST_POLICY)
        client_a, client_b = make_mock_client(), make_mock_client()

        with patch("tg_pool.orchestrator.ClientFactory.build", side_effect=[client_a, client_b]):
            await coordinator.get_replacement("+7000")
            await coordinator.get_replacement("+7001")

        await coordinator.close_promoted()

        client_a.disconnect.assert_awaited_once()
        client_b.disconnect.assert_awaited_once()

    async def test_close_promoted_swallows_disconnect_errors(self):
        spare = make_spare("+7002")
        coordinator = FailoverCoordinator([spare], FAST_POLICY)
        client = make_mock_client()
        client.disconnect = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("tg_pool.orchestrator.ClientFactory.build", return_value=client):
            await coordinator.get_replacement("+7001")

        await coordinator.close_promoted()  # must not raise
