from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from telethon import TelegramClient

from src.config import AccountConfig, TimingPolicy
from src.accounts.connection_manager import ClientFactory, ClientPool
from src.extraction.data_extraction import (
    NO_SHARD,
    BaseParsingStrategy,
    GroupMembersStrategy,
    ParsedUser,
    Shard,
    extract_members,
    extract_users,
)
from src.extraction.entity_resolver import describe_entity, estimate_entity_weight
from src.extraction.redis_dedup import RedisDedupSet
from src.monitoring.event_bus import AccountStatusEvent, EventBus, MetricUpdateEvent
from src.messaging.messaging_service import BatchReport, MessagePayload, send_notifications

if TYPE_CHECKING:
    from src.accounts.account_registry import AccountRegistry
    from src.accounts.warmup_policy import WarmupPolicy
    from src.extraction.data_extraction import LuaStrategySelector
    from src.extraction.exporter import DataExporter
    from src.messaging.auto_responder import AutoResponder
    from src.messaging.lua_storage import RedisRateLimiter
    from src.monitoring.monitor import LiveMonitor
    from src.extraction.user_filter import UserFilterPipeline

logger = logging.getLogger(__name__)


class FailoverCoordinator:
    """Hands out live replacement accounts from a spare pool; asyncio.Lock-protected since workers race to claim spares."""

    def __init__(
        self,
        spare_accounts: List[AccountConfig],
        policy: TimingPolicy,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._spares = list(spare_accounts)
        self._policy = policy
        self._dead: set = set()
        self._lock = asyncio.Lock()
        self._event_bus = event_bus
        # Tracked separately: promoted spares aren't in ClientPool._clients, so close_all() won't disconnect them.
        self._promoted: Dict[str, TelegramClient] = {}

    async def get_replacement(
        self,
        dead_phone: str,
    ) -> Optional[Tuple[TelegramClient, str]]:
        async with self._lock:
            self._dead.add(dead_phone)
            logger.warning(
                "Coordinator: %s marked DEAD. Spares left: %d",
                dead_phone, len(self._spares),
            )

            if self._event_bus is not None:
                await self._event_bus.publish(AccountStatusEvent(
                    phone=dead_phone, status="dead",
                    detail="Account died; coordinator searching for replacement",
                ))

            while self._spares:
                candidate = self._spares.pop(0)
                if candidate.phone in self._dead:
                    continue

                try:
                    client = ClientFactory.build(candidate)
                    await client.connect()
                    if not await client.is_user_authorized():
                        await client.disconnect()
                        logger.warning(
                            "Spare %s not authorized — skipping.", candidate.phone
                        )
                        continue

                    logger.info("Coordinator: replacement %s ready.", candidate.phone)

                    if self._event_bus is not None:
                        await self._event_bus.publish(AccountStatusEvent(
                            phone=candidate.phone, status="alive",
                            detail="Promoted from spare pool",
                        ))

                    self._promoted[candidate.phone] = client
                    return client, candidate.phone

                except Exception as exc:
                    logger.error(
                        "Spare %s failed to connect: %s", candidate.phone, exc
                    )

            logger.error("Coordinator: no spare accounts remaining.")
            return None

    async def close_promoted(self) -> None:
        """Disconnects every promoted spare client; call alongside pool.close_all() during cleanup."""
        if not self._promoted:
            return
        tasks = [
            self._safe_disconnect(phone, client)
            for phone, client in self._promoted.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._promoted.clear()

    @staticmethod
    async def _safe_disconnect(phone: str, client: TelegramClient) -> None:
        try:
            if client.is_connected():
                await client.disconnect()
                logger.info("Coordinator: promoted client %s disconnected.", phone)
        except Exception as exc:
            logger.warning("Coordinator: error disconnecting %s: %s", phone, exc)

    @property
    def dead_phones(self) -> frozenset:
        return frozenset(self._dead)


async def _gather_or_cancel(
    tasks: List[asyncio.Task],
    shutdown_event: Optional[asyncio.Event],
) -> List:
    """Runs tasks concurrently; if shutdown_event fires first, cancels everything and returns an empty list."""
    if shutdown_event is None:
        return await asyncio.gather(*tasks, return_exceptions=True)

    # asyncio.gather() returns a Future, not a coroutine — wrap in an async def so create_task() gets a coroutine.
    async def _run_all():
        return await asyncio.gather(*tasks, return_exceptions=True)

    gather_task = asyncio.create_task(_run_all(), name="extraction-gather")
    shutdown_task = asyncio.create_task(shutdown_event.wait(), name="shutdown-guard")

    done, pending = await asyncio.wait(
        [gather_task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for p in pending:
        p.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await p

    if shutdown_task in done:
        for t in tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        logger.warning("Extraction phase cancelled due to shutdown signal.")
        return []

    return gather_task.result()


async def orchestrate(
    accounts: List[AccountConfig],
    entity_identifier: str,
    payload: Optional[MessagePayload] = None,
    message: str = "Привет, мир",
    policy: Optional[TimingPolicy] = None,
    rate_limiter: Optional["RedisRateLimiter"] = None,
    spare_accounts: Optional[List[AccountConfig]] = None,
    monitor: Optional["LiveMonitor"] = None,
    event_bus: Optional[EventBus] = None,
    shutdown_event: Optional[asyncio.Event] = None,
    session_encryption_key: Optional[bytes] = None,
) -> BatchReport:
    if policy is None:
        policy = TimingPolicy()

    if payload is None:
        payload = MessagePayload(text=message)

    if not accounts:
        logger.error("orchestrate(): empty accounts list.")
        return BatchReport()

    coordinator: Optional[FailoverCoordinator] = None
    if spare_accounts:
        coordinator = FailoverCoordinator(
            spare_accounts=spare_accounts,
            policy=policy,
            event_bus=event_bus,
        )
        logger.info(
            "Failover coordinator ready: %d spare accounts.", len(spare_accounts)
        )

    logger.info(
        "=" * 60 + "\nOrchestrator START\n"
        "  accounts : %d (+%d spares)\n  entity   : %s\n"
        "  limiter  : %s\n  bus      : %s\n" + "=" * 60,
        len(accounts), len(spare_accounts or []),
        entity_identifier,
        "enabled" if rate_limiter else "disabled",
        "connected" if event_bus else "none",
    )

    pool = ClientPool(accounts=accounts, policy=policy, session_encryption_key=session_encryption_key)
    report = BatchReport()

    try:
        logger.info("--- Phase 0: Pool initialization ---")
        await pool.initialize()

        if not pool:
            logger.error("No clients active after initialization. Aborting.")
            return BatchReport()

        active_workers = pool.get_worker_pairs()

        if event_bus is not None:
            for _, phone in active_workers:
                await event_bus.publish(AccountStatusEvent(
                    phone=phone, status="alive", detail="Pool initialized"
                ))

        logger.info(
            "Phase 0: %d/%d clients active.", len(active_workers), len(accounts)
        )

        logger.info("--- Phase 1: Parallel extraction ---")

        extraction_tasks = [
            asyncio.create_task(
                extract_members(
                    client=client,
                    entity_identifier=entity_identifier,
                    policy=policy,
                ),
                name=f"extract-{phone}",
            )
            for client, phone in active_workers
        ]

        raw_results = await _gather_or_cancel(extraction_tasks, shutdown_event)

        if not raw_results and shutdown_event is not None and shutdown_event.is_set():
            logger.warning("Pipeline aborted during extraction phase.")
            return BatchReport()

        all_usernames: Set[str] = set()
        for i, result in enumerate(raw_results):
            if isinstance(result, Exception):
                logger.error(
                    "Extraction failed for %s: %s", active_workers[i][1], result
                )
            elif isinstance(result, set):
                all_usernames |= result

        logger.info("Phase 1: %d unique usernames collected.", len(all_usernames))

        if not all_usernames:
            logger.warning(
                "No usernames from '%s'. Skipping send.", entity_identifier
            )
            return BatchReport()

        filtered = all_usernames
        logger.info("--- Phase 2: %d recipients ---", len(filtered))

        if event_bus is not None:
            await event_bus.publish(MetricUpdateEvent(
                key="total_recipients", value=len(filtered)
            ))

        logger.info("--- Phase 3: Sending to %d recipients ---", len(filtered))

        report = await send_notifications(
            workers=active_workers,
            recipients=filtered,
            payload=payload,
            policy=policy,
            rate_limiter=rate_limiter,
            coordinator=coordinator,
            event_bus=event_bus,
            shutdown_event=shutdown_event,
        )

    finally:
        logger.info("--- Phase 4: Cleanup ---")
        await pool.close_all()
        if coordinator is not None:
            await coordinator.close_promoted()

    logger.info(
        "=" * 60 + "\nOrchestrator DONE\n  %s\n" + "=" * 60, report
    )
    return report


def _distribute_by_weight(weighted: List[Tuple[str, float]], n: int) -> List[List[str]]:
    """Greedy LPT: sorts by descending weight, assigns each to the least-loaded bucket — better makespan than round-robin for skewed source sizes."""
    buckets: List[List[str]] = [[] for _ in range(n)]
    loads = [0.0] * n
    for identifier, weight in sorted(weighted, key=lambda pair: pair[1], reverse=True):
        idx = min(range(n), key=lambda i: loads[i])
        buckets[idx].append(identifier)
        loads[idx] += weight
    return buckets


async def _weigh_entities(client: TelegramClient, entity_identifiers: List[str]) -> List[Tuple[str, float]]:
    """Estimates every entity's weight concurrently through a single client."""
    weights = await asyncio.gather(
        *(estimate_entity_weight(client, identifier) for identifier in entity_identifiers)
    )
    return list(zip(entity_identifiers, weights))


def _default_job_key(entity_identifiers: List[str]) -> str:
    """Deterministic hash of the source set, so a resumed run without an explicit job_key reuses the same RedisDedupSet state."""
    joined = ",".join(sorted(entity_identifiers))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


async def _dedup_against_redis(
    dedup: RedisDedupSet, job_key: str, users: Set[ParsedUser]
) -> Set[ParsedUser]:
    fresh: Set[ParsedUser] = set()
    for user in users:
        if not await dedup.already_seen(job_key, user.user_id):
            fresh.add(user)
    return fresh


# Guards a source against concurrent hits from separate parsing jobs sharing Redis (a job's own bucket assignment already prevents its own workers from colliding).
_PARSE_ANTIFLOOD_CAPACITY = 3
_PARSE_ANTIFLOOD_REFILL_RATE = 1 / 300.0


async def _collect_bucket(
    client: TelegramClient,
    phone: str,
    entities: List[str],
    strategy: BaseParsingStrategy,
    policy: TimingPolicy,
    antiflood_redis_client: Optional[Any] = None,
    strategy_selector: Optional["LuaStrategySelector"] = None,
    shard: Shard = NO_SHARD,
) -> Set[ParsedUser]:
    """
    shard=(index, total): this worker's slice when the same entities list is
    handed to `total` workers at once (see orchestrate_extraction_only,
    which shards every entity across the whole pool instead of giving whole
    entities to single workers). (0, 1) -- the default, used unchanged by
    orchestrate_multi_source -- means "I own these entities entirely".
    """
    combined: Set[ParsedUser] = set()
    for entity_id in entities:
        if antiflood_redis_client is not None:
            from src.messaging.lua_storage import RedisRateLimiter
            limiter = RedisRateLimiter(
                antiflood_redis_client,
                pool_id=f"parse:{entity_id}",
                capacity=_PARSE_ANTIFLOOD_CAPACITY,
                refill_rate=_PARSE_ANTIFLOOD_REFILL_RATE,
            )
            allowed, reason = await limiter.check_and_consume(entity_id)
            if not allowed:
                logger.warning("[%s] Skipping %s: anti-flood (%s)", phone, entity_id, reason)
                continue

        entity_strategy = strategy
        if strategy_selector is not None:
            info = await describe_entity(client, entity_id)
            entity_strategy = strategy_selector.select(
                kind=info.kind.name.lower(), is_forum=info.is_forum, estimated_weight=info.weight,
                has_discussion=info.has_discussion,
            )

        try:
            users = await extract_users(client, entity_id, entity_strategy, policy, shard=shard)
            combined |= users
        except Exception as exc:
            logger.error("[%s] Extraction failed for %s: %s", phone, entity_id, exc)
    return combined


async def orchestrate_multi_source(
    accounts: List[AccountConfig],
    entity_identifiers: List[str],
    payload: Optional[MessagePayload] = None,
    message: str = "Привет, мир",
    policy: Optional[TimingPolicy] = None,
    strategy: Optional[BaseParsingStrategy] = None,
    user_filter: Optional["UserFilterPipeline"] = None,
    exporter: Optional["DataExporter"] = None,
    rate_limiter: Optional["RedisRateLimiter"] = None,
    spare_accounts: Optional[List[AccountConfig]] = None,
    event_bus: Optional[EventBus] = None,
    shutdown_event: Optional[asyncio.Event] = None,
    session_encryption_key: Optional[bytes] = None,
    registry: Optional["AccountRegistry"] = None,
    warmup_policy: Optional["WarmupPolicy"] = None,
    redis_client: Optional[Any] = None,
    auto_responder: Optional["AutoResponder"] = None,
    strategy_selector: Optional["LuaStrategySelector"] = None,
    messages_per_account_min: int = 1,
    messages_per_account_max: Optional[int] = None,
    exclude_recipients: Optional[Set[str]] = None,
    worker_batch_size: Optional[int] = None,
    worker_batch_delay_sec: float = 0.0,
) -> BatchReport:
    if policy is None:
        policy = TimingPolicy()

    if payload is None:
        payload = MessagePayload(text=message)

    active_selector = (
        strategy_selector if (strategy is None and len(entity_identifiers) > 1) else None
    )
    if strategy is None:
        strategy = GroupMembersStrategy()

    if not accounts:
        logger.error("orchestrate_multi_source(): empty accounts list.")
        return BatchReport()

    if not entity_identifiers:
        logger.warning("orchestrate_multi_source(): no entity_identifiers provided.")
        return BatchReport()

    coordinator: Optional[FailoverCoordinator] = None
    if spare_accounts:
        coordinator = FailoverCoordinator(
            spare_accounts=spare_accounts,
            policy=policy,
            event_bus=event_bus,
        )

    logger.info(
        "=" * 60 + "\nMulti-Source Orchestrator START\n"
        "  accounts : %d  entities: %d  strategy: %s\n" + "=" * 60,
        len(accounts), len(entity_identifiers), type(strategy).__name__,
    )

    pool = ClientPool(accounts=accounts, policy=policy, session_encryption_key=session_encryption_key)
    report = BatchReport()

    try:
        await pool.initialize()
        if not pool:
            logger.error("No active clients after init. Aborting.")
            return BatchReport()

        active_workers = pool.get_worker_pairs()

        if event_bus is not None:
            for _, phone in active_workers:
                await event_bus.publish(AccountStatusEvent(
                    phone=phone, status="alive", detail="Multi-source pool initialized"
                ))

        # Attached now; auto_responder.detach_all() runs in the finally block below.
        if auto_responder is not None:
            for client, phone in active_workers:
                auto_responder.attach(client, phone)

        # Unknown account age is treated as day 0 (safest default) for both the delay multiplier and the daily cap.
        warmup_multipliers: Optional[Dict[str, float]] = None
        warmup_limiters: Optional[Dict[str, "RedisRateLimiter"]] = None
        if warmup_policy is not None and registry is not None:
            now = datetime.now(timezone.utc)
            ages: Dict[str, float] = {}
            for _, phone in active_workers:
                entry = registry.get(phone)
                if entry is not None and entry.first_seen is not None:
                    ages[phone] = (now - entry.first_seen).total_seconds() / 86400.0
                else:
                    ages[phone] = 0.0

            warmup_multipliers = {
                phone: warmup_policy.delay_multiplier(age) for phone, age in ages.items()
            }

            if redis_client is not None:
                from src.messaging.lua_storage import RedisRateLimiter
                warmup_limiters = {}
                for phone, age in ages.items():
                    cap = warmup_policy.daily_message_cap(age)
                    warmup_limiters[phone] = RedisRateLimiter(
                        redis_client, pool_id=f"warmup:{phone}",
                        capacity=cap, refill_rate=cap / 86400.0, cost=1,
                    )

        weighted_entities = await _weigh_entities(active_workers[0][0], entity_identifiers)
        buckets = _distribute_by_weight(weighted_entities, len(active_workers))
        logger.info("Phase 1: %d workers, %d entities distributed", len(active_workers), len(entity_identifiers))

        extraction_tasks = [
            asyncio.create_task(
                _collect_bucket(client, phone, bucket, strategy, policy, strategy_selector=active_selector),
                name=f"bucket-{phone}",
            )
            for (client, phone), bucket in zip(active_workers, buckets)
            if bucket
        ]

        raw_results = await _gather_or_cancel(extraction_tasks, shutdown_event)

        if not raw_results and shutdown_event is not None and shutdown_event.is_set():
            logger.warning("Multi-source pipeline aborted during extraction.")
            return BatchReport()

        all_users: Set[ParsedUser] = set()
        for result in raw_results:
            if isinstance(result, Exception):
                logger.error("Bucket extraction error: %s", result)
            elif isinstance(result, set):
                all_users |= result

        logger.info("Phase 2: %d unique users collected.", len(all_users))

        # Exported before filtering, so the exporter sees everyone found (not just who got messaged).
        if exporter is not None:
            exporter.add_many(all_users)

        if user_filter is not None:
            filtered_list = user_filter.apply(all_users)
            logger.info("Phase 2: %d users after filtering.", len(filtered_list))
        else:
            filtered_list = list(all_users)

        if not filtered_list:
            logger.warning("No users after filtering. Skipping send.")
            return BatchReport()

        recipients: Set[str] = {u.username for u in filtered_list if u.username}
        if exclude_recipients:
            recipients -= exclude_recipients
        if not recipients:
            logger.warning("No usernames in filtered users. Skipping send.")
            return BatchReport()

        if event_bus is not None:
            await event_bus.publish(MetricUpdateEvent(key="total_recipients", value=len(recipients)))

        # first_name/last_name/username placeholders for payload.text, captured here before recipients is reduced to bare usernames below.
        personalization = {
            u.username: {
                "first_name": u.first_name,
                "last_name": u.last_name,
                "username": u.username,
            }
            for u in filtered_list if u.username
        }

        logger.info("Phase 3: Sending to %d recipients.", len(recipients))
        report = await send_notifications(
            workers=active_workers,
            recipients=recipients,
            payload=payload,
            policy=policy,
            rate_limiter=rate_limiter,
            coordinator=coordinator,
            event_bus=event_bus,
            shutdown_event=shutdown_event,
            personalization=personalization,
            warmup_multipliers=warmup_multipliers,
            warmup_limiters=warmup_limiters,
            messages_per_account_min=messages_per_account_min,
            messages_per_account_max=messages_per_account_max,
            worker_batch_size=worker_batch_size,
            worker_batch_delay_sec=worker_batch_delay_sec,
        )

    finally:
        if auto_responder is not None:
            auto_responder.detach_all()
        await pool.close_all()
        if coordinator is not None:
            await coordinator.close_promoted()

    logger.info(
        "=" * 60 + "\nMulti-Source Orchestrator DONE\n  %s\n" + "=" * 60, report
    )
    return report


_MAX_TARGET_CYCLES_DEFAULT = 20


async def orchestrate_until_target(
    exact_total_target: int,
    max_cycles: int = _MAX_TARGET_CYCLES_DEFAULT,
    **kwargs: Any,
) -> BatchReport:
    """Repeats orchestrate_multi_source() cycles -- excluding previously reached
    recipients each time -- until exact_total_target successes are reached, a
    cycle reaches no new recipients (source pool exhausted), or max_cycles is
    hit. Accepts the same keyword arguments as orchestrate_multi_source()
    except exclude_recipients, which it manages internally.
    """
    shutdown_event: Optional[asyncio.Event] = kwargs.get("shutdown_event")
    combined = BatchReport()
    exclude_recipients: Set[str] = set()

    for cycle in range(1, max_cycles + 1):
        if shutdown_event is not None and shutdown_event.is_set():
            break
        if exact_total_target - combined.succeeded <= 0:
            break

        cycle_report = await orchestrate_multi_source(
            **kwargs, exclude_recipients=exclude_recipients or None,
        )
        combined.merge_from(cycle_report)

        if not cycle_report.sent_recipients:
            logger.info(
                "orchestrate_until_target: cycle %d reached no new recipients, stopping (got %d/%d).",
                cycle, combined.succeeded, exact_total_target,
            )
            break
        exclude_recipients |= cycle_report.sent_recipients

    return combined


async def run_with_repeat(
    run_once: "Callable[[], Awaitable[BatchReport]]",
    shutdown_event: Optional[asyncio.Event] = None,
    repeat_every_hours: Optional[float] = None,
) -> BatchReport:
    """Runs run_once() once, then -- if repeat_every_hours is set -- keeps
    re-running it after sleeping that many hours, until shutdown_event fires.
    Combines every cycle's BatchReport into one cumulative report."""
    combined = BatchReport()
    while True:
        combined.merge_from(await run_once())
        if repeat_every_hours is None or (shutdown_event is not None and shutdown_event.is_set()):
            break

        logger.info("Campaign cycle complete. Repeating in %.2fh.", repeat_every_hours)
        if shutdown_event is None:
            await asyncio.sleep(repeat_every_hours * 3600)
        else:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=repeat_every_hours * 3600)
            except asyncio.TimeoutError:
                pass
            if shutdown_event.is_set():
                break

    return combined


async def orchestrate_extraction_only(
    accounts: List[AccountConfig],
    entity_identifiers: List[str],
    strategy: Optional[BaseParsingStrategy] = None,
    user_filter: Optional["UserFilterPipeline"] = None,
    exporter: Optional["DataExporter"] = None,
    policy: Optional[TimingPolicy] = None,
    spare_accounts: Optional[List[AccountConfig]] = None,
    event_bus: Optional[EventBus] = None,
    shutdown_event: Optional[asyncio.Event] = None,
    session_encryption_key: Optional[bytes] = None,
    redis_client: Optional[Any] = None,
    job_key: Optional[str] = None,
    strategy_selector: Optional["LuaStrategySelector"] = None,
) -> "DataExporter":
    """Unlike orchestrate_multi_source(), exports the FILTERED set — there's no send phase to keep "found" separate from "messaged"."""
    if policy is None:
        policy = TimingPolicy()

    # No len(entity_identifiers) > 1 gate here (unlike orchestrate_multi_source):
    # "smart" per-entity selection is an explicit user choice (strategy=None
    # means they picked auto/smart mode), so it applies even to a single
    # target -- that's the common case the feature exists for.
    active_selector = strategy_selector if strategy is None else None
    if strategy is None:
        strategy = GroupMembersStrategy()

    if exporter is None:
        from src.extraction.exporter import DataExporter
        exporter = DataExporter()

    if not accounts:
        logger.error("orchestrate_extraction_only(): empty accounts list.")
        return exporter

    if not entity_identifiers:
        logger.warning("orchestrate_extraction_only(): no entity_identifiers provided.")
        return exporter

    coordinator: Optional[FailoverCoordinator] = None
    if spare_accounts:
        coordinator = FailoverCoordinator(
            spare_accounts=spare_accounts, policy=policy, event_bus=event_bus,
        )

    logger.info(
        "=" * 60 + "\nExtraction-Only Orchestrator START\n"
        "  accounts : %d  entities: %d  strategy: %s\n" + "=" * 60,
        len(accounts), len(entity_identifiers), type(strategy).__name__,
    )

    pool = ClientPool(accounts=accounts, policy=policy, session_encryption_key=session_encryption_key)

    try:
        await pool.initialize()
        if not pool:
            logger.error("No active clients after init. Aborting.")
            return exporter

        active_workers = pool.get_worker_pairs()

        if event_bus is not None:
            for _, phone in active_workers:
                await event_bus.publish(AccountStatusEvent(
                    phone=phone, status="alive", detail="Extraction-only pool initialized"
                ))

        # Every worker covers every entity, each as a 1/num_workers shard --
        # not whole-entity-per-worker bucketing. A single target still keeps
        # the whole pool busy instead of leaving every account but one idle,
        # and load balances naturally (no weight estimate needed) since each
        # worker's share of every entity is identical by construction.
        num_workers = len(active_workers)
        logger.info(
            "Phase 1: %d workers, %d entities, each entity split %d ways",
            num_workers, len(entity_identifiers), num_workers,
        )

        extraction_tasks = [
            asyncio.create_task(
                _collect_bucket(
                    client, phone, entity_identifiers, strategy, policy,
                    antiflood_redis_client=redis_client, strategy_selector=active_selector,
                    shard=(worker_index, num_workers),
                ),
                name=f"extract-only-shard-{phone}",
            )
            for worker_index, (client, phone) in enumerate(active_workers)
        ]

        raw_results = await _gather_or_cancel(extraction_tasks, shutdown_event)

        if not raw_results and shutdown_event is not None and shutdown_event.is_set():
            logger.warning("Extraction-only pipeline aborted during extraction.")
            return exporter

        dedup = RedisDedupSet(redis_client) if redis_client is not None else None
        effective_job_key = job_key or _default_job_key(entity_identifiers)

        all_users: Set[ParsedUser] = set()
        for result in raw_results:
            if isinstance(result, Exception):
                logger.error("Bucket extraction error: %s", result)
            elif isinstance(result, set):
                if dedup is not None:
                    result = await _dedup_against_redis(dedup, effective_job_key, result)
                all_users |= result

        logger.info("Phase 2: %d unique users collected.", len(all_users))

        if user_filter is not None:
            filtered_users = user_filter.apply(all_users)
            logger.info(
                "Phase 2: %d users after filtering (of %d collected).",
                len(filtered_users), len(all_users),
            )
        else:
            filtered_users = list(all_users)

        exporter.add_many(filtered_users)

        if event_bus is not None:
            await event_bus.publish(MetricUpdateEvent(key="total_recipients", value=len(filtered_users)))

    finally:
        await pool.close_all()
        if coordinator is not None:
            await coordinator.close_promoted()

    logger.info(
        "=" * 60 + "\nExtraction-Only Orchestrator DONE\n  %d users, %d sources\n" + "=" * 60,
        exporter.total, len(exporter.sources),
    )
    return exporter
