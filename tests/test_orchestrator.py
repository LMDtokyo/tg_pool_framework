"""
tests/test_orchestrator.py — Integration-style tests for src/orchestrator.py.

Тестирует сквозной пайплайн с полностью мокированными зависимостями:
  - ClientPool (initialize / close_all / get_worker_pairs)
  - extract_members (возвращает Set[str])
  - send_notifications (возвращает BatchReport)

Почему мок, а не реальные клиенты?
  Юнит-тест не должен зависеть от сети/аккаунтов.
  Мокирование на уровне модулей гарантирует изоляцию:
  тестируем только логику orchestrate(), а не Telethon.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis as fakeredis_aio
import pytest

from src.config import AccountConfig, TimingPolicy
from src.extraction.data_extraction import ParsedUser
from src.extraction.entity_resolver import EntityInfo, EntityKind
from src.messaging.messaging_service import BatchReport
from src.orchestrator import _collect_bucket, _distribute_by_weight, _weigh_entities, orchestrate


FAST_POLICY = TimingPolicy(
    base_delay_sec=0.0,
    jitter_sec=0.0,
    inter_message_delay_sec=0.0,
    inter_message_jitter_sec=0.0,
    startup_jitter_max_sec=0.0,
    max_flood_retries=3,
)


def make_account(phone: str = "+79001234567") -> AccountConfig:
    return AccountConfig(
        api_id=12345,
        api_hash="a" * 32,
        phone=phone,
    )


def make_batch_report(total: int = 5, succeeded: int = 5) -> BatchReport:
    return BatchReport(
        total=total,
        succeeded=succeeded,
        failed=total - succeeded,
    )


def make_mock_pool(worker_pairs=None) -> MagicMock:
    """Строит мок ClientPool с нужным поведением."""
    if worker_pairs is None:
        worker_pairs = [(MagicMock(), "+79001234567")]

    pool = MagicMock()
    pool.initialize = AsyncMock()
    pool.close_all = AsyncMock()
    pool.get_worker_pairs = MagicMock(return_value=worker_pairs)
    pool.__bool__ = MagicMock(return_value=bool(worker_pairs))
    pool.__len__ = MagicMock(return_value=len(worker_pairs))
    return pool


# ---------------------------------------------------------------------------
# Tests: базовые сценарии
# ---------------------------------------------------------------------------

class TestOrchestrateBasic:
    async def test_empty_accounts_returns_empty_report(self):
        report = await orchestrate(
            accounts=[],
            entity_identifier="@test",
            policy=FAST_POLICY,
        )
        assert report.total == 0
        assert report.succeeded == 0

    async def test_full_pipeline_success(self):
        """
        Счастливый путь: извлекли участников → разослали → вернули отчёт.
        """
        accounts = [make_account("+79001111111"), make_account("+79002222222")]
        worker_pairs = [(MagicMock(), "+79001111111"), (MagicMock(), "+79002222222")]
        mock_pool = make_mock_pool(worker_pairs=worker_pairs)
        extracted_usernames = {"alice", "bob", "carol"}
        expected_report = make_batch_report(total=3, succeeded=3)

        with (
            patch("src.orchestrator.ClientPool", return_value=mock_pool),
            patch(
                "src.orchestrator.extract_members",
                new=AsyncMock(return_value=extracted_usernames),
            ),
            patch(
                "src.orchestrator.send_notifications",
                new=AsyncMock(return_value=expected_report),
            ),
        ):
            report = await orchestrate(
                accounts=accounts,
                entity_identifier="@testgroup",
                message="Привет, мир",
                policy=FAST_POLICY,
            )

        mock_pool.initialize.assert_called_once()
        mock_pool.close_all.assert_called_once()
        assert report.total == 3
        assert report.succeeded == 3
        assert report.failed == 0

    async def test_cleanup_called_even_on_extraction_error(self):
        """
        close_all() должен вызываться ВСЕГДА через try/finally,
        даже если extract_members() выбрасывает исключение.
        """
        accounts = [make_account()]
        mock_pool = make_mock_pool()

        with (
            patch("src.orchestrator.ClientPool", return_value=mock_pool),
            patch(
                "src.orchestrator.extract_members",
                new=AsyncMock(side_effect=RuntimeError("network error")),
            ),
        ):
            report = await orchestrate(
                accounts=accounts,
                entity_identifier="@testgroup",
                policy=FAST_POLICY,
            )

        mock_pool.close_all.assert_called_once()

    async def test_no_usernames_skips_send(self):
        """
        Если extract_members() вернул пустой set — send_notifications()
        не должен вызываться.
        """
        accounts = [make_account()]
        mock_pool = make_mock_pool()

        with (
            patch("src.orchestrator.ClientPool", return_value=mock_pool),
            patch(
                "src.orchestrator.extract_members",
                new=AsyncMock(return_value=set()),
            ),
            patch("src.orchestrator.send_notifications") as mock_send,
        ):
            report = await orchestrate(
                accounts=accounts,
                entity_identifier="@emptygroup",
                policy=FAST_POLICY,
            )

        mock_send.assert_not_called()
        assert report.total == 0


# ---------------------------------------------------------------------------
# Tests: дедупликация usernames между воркерами
# ---------------------------------------------------------------------------

class TestOrchestrateDeduplication:
    async def test_usernames_from_multiple_workers_are_merged(self):
        """
        Если два воркера собрали пересекающиеся множества username —
        итоговое множество должно быть их union (без дублей).
        """
        accounts = [make_account("+7001"), make_account("+7002")]
        worker_pairs = [(MagicMock(), "+7001"), (MagicMock(), "+7002")]
        mock_pool = make_mock_pool(worker_pairs=worker_pairs)

        set_1 = {"alice", "bob", "charlie"}
        set_2 = {"bob", "charlie", "dave"}  # bob и charlie — дубли
        expected_union = {"alice", "bob", "charlie", "dave"}

        call_count = 0

        async def side_effect_extract(client, entity_identifier, policy):
            nonlocal call_count
            call_count += 1
            return set_1 if call_count == 1 else set_2

        captured_recipients = None

        async def mock_send(workers, recipients, payload=None, policy=None, rate_limiter=None, coordinator=None, event_bus=None, shutdown_event=None):
            nonlocal captured_recipients
            captured_recipients = recipients
            return make_batch_report(total=len(recipients), succeeded=len(recipients))

        with (
            patch("src.orchestrator.ClientPool", return_value=mock_pool),
            patch("src.orchestrator.extract_members", side_effect=side_effect_extract),
            patch("src.orchestrator.send_notifications", side_effect=mock_send),
        ):
            await orchestrate(
                accounts=accounts,
                entity_identifier="@group",
                policy=FAST_POLICY,
            )

        assert captured_recipients == expected_union, (
            f"Ожидали union={expected_union}, получили {captured_recipients}"
        )


# ---------------------------------------------------------------------------
# Tests: Pool initialization failure
# ---------------------------------------------------------------------------

class TestOrchestratePoolFailure:
    async def test_empty_pool_after_init_returns_empty_report(self):
        """
        Если после initialize() нет активных клиентов — возвращаем пустой
        BatchReport и не вызываем send.
        """
        accounts = [make_account()]
        mock_pool = make_mock_pool(worker_pairs=[])
        mock_pool.__bool__ = MagicMock(return_value=False)
        mock_pool.__len__ = MagicMock(return_value=0)

        with (
            patch("src.orchestrator.ClientPool", return_value=mock_pool),
            patch("src.orchestrator.send_notifications") as mock_send,
        ):
            report = await orchestrate(
                accounts=accounts,
                entity_identifier="@group",
                policy=FAST_POLICY,
            )

        mock_send.assert_not_called()
        assert report.total == 0

    async def test_default_policy_used_when_none_provided(self):
        """
        Если policy=None — orchestrate должен создать TimingPolicy() по умолчанию.
        """
        accounts = [make_account()]
        mock_pool = make_mock_pool()

        with (
            patch("src.orchestrator.ClientPool", return_value=mock_pool),
            patch(
                "src.orchestrator.extract_members",
                new=AsyncMock(return_value=set()),
            ),
        ):
            report = await orchestrate(
                accounts=accounts,
                entity_identifier="@group",
            )

        assert report is not None


# ---------------------------------------------------------------------------
# Tests: _distribute_by_weight() — LPT greedy bin-packing
# ---------------------------------------------------------------------------

class TestDistributeByWeight:
    def test_one_oversized_source_gets_its_own_bucket(self):
        weighted = [("huge", 1000.0), ("small1", 1.0), ("small2", 1.0), ("small3", 1.0)]

        buckets = _distribute_by_weight(weighted, 2)

        assert ["huge"] in buckets
        other = next(b for b in buckets if b != ["huge"])
        assert set(other) == {"small1", "small2", "small3"}

    def test_equal_weights_matches_round_robin_bucket_sizes(self):
        weighted = [("a", 1.0), ("b", 1.0), ("c", 1.0), ("d", 1.0), ("e", 1.0)]

        buckets = _distribute_by_weight(weighted, 3)

        assert sorted(len(b) for b in buckets) == [1, 2, 2]
        assert sorted(item for bucket in buckets for item in bucket) == ["a", "b", "c", "d", "e"]

    def test_unknown_weights_fall_back_to_evenly_sized_buckets(self):
        """All weights == 1.0 (estimate_entity_weight()'s fallback) behaves like round-robin."""
        weighted = [(f"e{i}", 1.0) for i in range(6)]

        buckets = _distribute_by_weight(weighted, 3)

        assert sorted(len(b) for b in buckets) == [2, 2, 2]

    def test_empty_items(self):
        assert _distribute_by_weight([], 3) == [[], [], []]


# ---------------------------------------------------------------------------
# Tests: _weigh_entities() — concurrent per-entity weight estimation
# ---------------------------------------------------------------------------

class TestWeighEntities:
    async def test_pairs_each_identifier_with_its_estimated_weight(self):
        client = MagicMock()
        mock_estimate = AsyncMock(side_effect=[5.0, 10.0])

        with patch("src.orchestrator.estimate_entity_weight", mock_estimate):
            result = await _weigh_entities(client, ["@e1", "@e2"])

        assert result == [("@e1", 5.0), ("@e2", 10.0)]
        assert mock_estimate.call_count == 2
        mock_estimate.assert_any_call(client, "@e1")
        mock_estimate.assert_any_call(client, "@e2")


# ---------------------------------------------------------------------------
# Tests: _collect_bucket() per-source anti-flood (antiflood_redis_client)
# ---------------------------------------------------------------------------

class TestCollectBucketAntiflood:
    async def test_no_redis_client_means_no_throttling(self):
        users = {ParsedUser(user_id=1, username="alice")}

        with patch("src.orchestrator.extract_users", new=AsyncMock(return_value=users)):
            results = [
                await _collect_bucket(MagicMock(), "+1", ["@shared"], MagicMock(), FAST_POLICY)
                for _ in range(5)
            ]

        assert all(result == users for result in results)

    async def test_repeated_calls_for_same_entity_throttled_after_capacity(self):
        """
        Simulates several *separate* jobs sharing one Redis all targeting the
        same entity -- only the first _PARSE_ANTIFLOOD_CAPACITY calls should
        get through; the rest are skipped (empty set) rather than erroring.
        """
        redis_client = fakeredis_aio.FakeRedis()
        users = {ParsedUser(user_id=1, username="alice")}

        with patch("src.orchestrator.extract_users", new=AsyncMock(return_value=users)):
            results = [
                await _collect_bucket(
                    MagicMock(), "+1", ["@shared"], MagicMock(), FAST_POLICY,
                    antiflood_redis_client=redis_client,
                )
                for _ in range(4)
            ]

        assert results[0] == users
        assert results[1] == users
        assert results[2] == users
        assert results[3] == set()

    async def test_different_entities_have_independent_buckets(self):
        redis_client = fakeredis_aio.FakeRedis()
        users_a = {ParsedUser(user_id=1, username="alice")}
        users_b = {ParsedUser(user_id=2, username="bob")}

        async def fake_extract_users(client, entity_id, strategy, policy):
            return users_a if entity_id == "@a" else users_b

        with patch("src.orchestrator.extract_users", new=AsyncMock(side_effect=fake_extract_users)):
            # Exhaust @a's bucket, @b should be unaffected.
            for _ in range(3):
                await _collect_bucket(
                    MagicMock(), "+1", ["@a"], MagicMock(), FAST_POLICY,
                    antiflood_redis_client=redis_client,
                )
            throttled = await _collect_bucket(
                MagicMock(), "+1", ["@a"], MagicMock(), FAST_POLICY,
                antiflood_redis_client=redis_client,
            )
            still_allowed = await _collect_bucket(
                MagicMock(), "+1", ["@b"], MagicMock(), FAST_POLICY,
                antiflood_redis_client=redis_client,
            )

        assert throttled == set()
        assert still_allowed == users_b


# ---------------------------------------------------------------------------
# Tests: _collect_bucket() per-entity strategy_selector
# ---------------------------------------------------------------------------

class TestCollectBucketStrategySelector:
    async def test_no_selector_uses_fixed_strategy_for_every_entity(self):
        fixed_strategy = MagicMock(name="fixed_strategy")
        used_strategies = []

        async def fake_extract_users(client, entity_id, strategy, policy):
            used_strategies.append(strategy)
            return set()

        with patch("src.orchestrator.extract_users", new=AsyncMock(side_effect=fake_extract_users)):
            await _collect_bucket(MagicMock(), "+1", ["@a", "@b"], fixed_strategy, FAST_POLICY)

        assert used_strategies == [fixed_strategy, fixed_strategy]

    async def test_selector_picks_strategy_per_entity(self):
        selector = MagicMock()
        strategy_a = MagicMock(name="strategy_a")
        strategy_b = MagicMock(name="strategy_b")
        selector.select.side_effect = [strategy_a, strategy_b]

        info_a = EntityInfo(weight=10.0, kind=EntityKind.CHAT, is_forum=False)
        info_b = EntityInfo(weight=20.0, kind=EntityKind.SUPERGROUP, is_forum=True)

        used_strategies = []

        async def fake_extract_users(client, entity_id, strategy, policy):
            used_strategies.append(strategy)
            return set()

        with (
            patch("src.orchestrator.describe_entity", new=AsyncMock(side_effect=[info_a, info_b])),
            patch("src.orchestrator.extract_users", new=AsyncMock(side_effect=fake_extract_users)),
        ):
            await _collect_bucket(
                MagicMock(), "+1", ["@a", "@b"], MagicMock(), FAST_POLICY,
                strategy_selector=selector,
            )

        assert used_strategies == [strategy_a, strategy_b]
        selector.select.assert_any_call(kind="chat", is_forum=False, estimated_weight=10.0)
        selector.select.assert_any_call(kind="supergroup", is_forum=True, estimated_weight=20.0)
