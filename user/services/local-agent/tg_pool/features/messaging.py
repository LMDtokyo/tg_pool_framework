from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import List

import tg_pool.bootstrap as bootstrap
from tg_pool.config import AccountConfig


def build_rate_limiter(redis_client=None):
    """Reuses redis_client if given (shared with the warm-up ramp) instead of opening a new connection."""
    client = redis_client if redis_client is not None else bootstrap.build_redis_client()
    if client is None:
        return None
    from tg_pool.messaging.lua_storage import RedisRateLimiter
    refill_rate = bootstrap.env_float("RATE_LIMIT_TOKENS_PER_SEC", "1.0")
    capacity = bootstrap.env_int("RATE_LIMIT_BURST", "5")
    fail_mode = os.getenv("RATE_LIMIT_FAIL_MODE", "open")
    return RedisRateLimiter(
        client, refill_rate=refill_rate, capacity=capacity, fail_mode=fail_mode
    )


def build_warmup_policy():
    if os.getenv("WARMUP_ENABLED", "0").lower() not in ("1", "true", "yes"):
        return None
    from tg_pool.accounts.warmup_policy import WarmupPolicy
    return WarmupPolicy(
        duration_days=bootstrap.env_float("WARMUP_DURATION_DAYS", "7"),
        min_multiplier=bootstrap.env_float("WARMUP_MIN_MULTIPLIER", "3.0"),
        max_daily_messages_day0=bootstrap.env_int("WARMUP_MAX_DAILY_DAY0", "10"),
        max_daily_messages_full=bootstrap.env_int("WARMUP_MAX_DAILY_FULL", "200"),
    )


def build_auto_responder():
    if os.getenv("AUTO_REPLY_ENABLED", "0").lower() not in ("1", "true", "yes"):
        return None
    from tg_pool.messaging.auto_responder import AutoResponder
    from tg_pool.scripting.lua_engine import LuaEngine
    scripts_dir = os.getenv("AUTO_REPLY_SCRIPTS_DIR", "scripts/auto_reply")
    engine = LuaEngine(scripts_dir)
    return AutoResponder(engine)


def build_payload():
    from tg_pool.messaging.messaging_service import MessagePayload

    media_paths_raw = os.getenv("TG_MEDIA_PATHS", "").strip()
    media_paths = [p.strip() for p in media_paths_raw.split(",") if p.strip()] or None

    bot_relay_ids_raw = os.getenv("TG_BOT_RELAY_MESSAGE_IDS", "").strip()
    bot_relay_ids = [int(x) for x in bot_relay_ids_raw.split(",") if x.strip().isdigit()] or None

    schedule_at_raw = os.getenv("TG_SCHEDULE_AT", "").strip()
    schedule_at = None
    if schedule_at_raw:
        try:
            schedule_at = datetime.fromisoformat(schedule_at_raw)
        except ValueError:
            pass

    return MessagePayload(
        text=os.getenv("TG_MESSAGE", "Привет!"),
        media_path=os.getenv("TG_MEDIA_PATH") or None,
        media_paths=media_paths,
        media_kind=os.getenv("TG_MEDIA_KIND", "auto").strip() or "auto",
        buttons_raw=os.getenv("TG_BUTTONS") or None,
        parse_mode=os.getenv("TG_PARSE_MODE", "markdown") or None,
        silent=os.getenv("TG_SILENT", "0").lower() in ("1", "true", "yes"),
        link_preview=os.getenv("TG_LINK_PREVIEW", "1").lower() in ("1", "true", "yes"),
        forward_link=os.getenv("TG_FORWARD_LINK") or None,
        bot_relay_username=os.getenv("TG_BOT_RELAY_USERNAME") or None,
        bot_relay_message_ids=bot_relay_ids,
        schedule_at=schedule_at,
        pin_after_send=os.getenv("TG_PIN_AFTER_SEND", "0").lower() in ("1", "true", "yes"),
    )


async def _run_health_check_preflight(accounts, policy, health_checker, registry, logger) -> list:
    from tg_pool.accounts.health_checker import AccountStatus
    deep = os.getenv("HEALTH_DEEP_CHECK", "0").lower() in ("1", "true", "yes")

    logger.info("Проверка здоровья пула: %d аккаунтов (deep=%s)…", len(accounts), deep)
    await registry.register_many(accounts)

    report = await health_checker.check_pool_health(accounts, deep_check=deep)
    logger.info(report.summary())

    for result in report.results:
        await registry.update_state(result.phone, result.account_state)

    banned = report.banned + report.spamblocked
    if banned:
        logger.warning(
            "Исключены %d аккаунтов (бан/спамблок): %s", len(banned), [r.phone for r in banned]
        )
    if report.unauthorized:
        logger.warning(
            "Исключены %d аккаунтов (требуют повторного входа, не забанены): %s",
            len(report.unauthorized), [r.phone for r in report.unauthorized],
        )

    alive_phones = {
        entry.account.phone
        for entry in registry.query().filter_by_status(AccountStatus.ALIVE).execute()
    }
    return [acc for acc in accounts if acc.phone in alive_phones]


async def _proxy_preflight(accounts: List[AccountConfig], logger: logging.Logger) -> List[AccountConfig]:
    """PROXY_PREFLIGHT_STRICT excludes accounts with a dead proxy instead of just warning about them."""
    if os.getenv("PROXY_PREFLIGHT_CHECK_ENABLED", "0").lower() not in ("1", "true", "yes"):
        return accounts

    from tg_pool.proxy.proxy_checker import check_account_proxies
    results = await check_account_proxies(accounts)
    if not results:
        return accounts

    dead_phones = {phone for phone, state in results.items() if not state.is_active}
    if dead_phones:
        logger.warning(
            "Прокси недоступны для %d аккаунтов: %s", len(dead_phones), sorted(dead_phones),
        )

    if dead_phones and os.getenv("PROXY_PREFLIGHT_STRICT", "0").lower() in ("1", "true", "yes"):
        accounts = [a for a in accounts if a.phone not in dead_phones]
        logger.info("PROXY_PREFLIGHT_STRICT: исключено %d аккаунтов с мёртвым прокси.", len(dead_phones))

    return accounts


async def run(shutdown_event: asyncio.Event, logger: logging.Logger) -> None:
    target = os.getenv("TG_TARGET_ENTITY", "")
    if not target:
        logger.error("TG_TARGET_ENTITY не задан.")
        return

    # Checked first: exiting here after clients/tasks already exist would skip their cleanup.
    session_encryption_key = bootstrap.build_session_encryption_key(logger)

    from tg_pool.config import TimingPolicy
    from tg_pool.monitoring.event_bus import EventBus
    from tg_pool.monitoring.monitor import LiveMonitor
    from tg_pool.orchestrator import orchestrate_multi_source, orchestrate_until_target, run_with_repeat

    policy = TimingPolicy(
        base_delay_sec=bootstrap.env_float("DELAY_BASE", "2.0"),
        jitter_sec=bootstrap.env_float("DELAY_JITTER", "1.5"),
        inter_message_delay_sec=bootstrap.env_float("MSG_DELAY", "3.0"),
        inter_message_jitter_sec=bootstrap.env_float("MSG_JITTER", "2.0"),
        max_flood_retries=bootstrap.env_int("MAX_RETRIES", "5"),
        startup_jitter_max_sec=bootstrap.env_float("STARTUP_JITTER", "3.0"),
    )

    event_bus = EventBus()

    primary, spares = bootstrap.load_accounts()
    primary = primary + await bootstrap.load_tdata_accounts()
    if not primary:
        logger.error(
            "Аккаунты не найдены. Заполните ACCOUNTS_DIR или TG_API_ID_1/... в .env"
        )
        return

    primary = await _proxy_preflight(primary, logger)
    if not primary:
        logger.error("После проверки прокси не осталось аккаунтов.")
        return

    logger.info(
        "Загружено: %d основных аккаунтов, %d резервных.", len(primary), len(spares)
    )

    db_session_factory = bootstrap.build_db_session_factory()

    from tg_pool.accounts.account_registry import AccountRegistry
    registry = AccountRegistry(repository=bootstrap.build_account_repository(db_session_factory))
    await registry.load_from_repository()

    account_folder = os.getenv("CAMPAIGN_ACCOUNT_FOLDER", "").strip()
    if account_folder:
        primary = [a for a in primary if (e := registry.get(a.phone)) and e.folder == account_folder]
        spares = [a for a in spares if (e := registry.get(a.phone)) and e.folder == account_folder]
        if not primary:
            logger.error("В папке %r нет аккаунтов.", account_folder)
            return

    health_checker = bootstrap.build_health_checker(policy, event_bus)

    if os.getenv("HEALTH_CHECK_ENABLED", "0").lower() in ("1", "true", "yes"):
        primary = await _run_health_check_preflight(primary, policy, health_checker, registry, logger)
        if not primary:
            logger.error("После проверки здоровья не осталось живых аккаунтов.")
            return

    cooldown_task: "asyncio.Task | None" = None
    if os.getenv("COOLDOWN_SCHEDULER_ENABLED", "0").lower() in ("1", "true", "yes"):
        from tg_pool.accounts.cooldown_scheduler import CooldownScheduler
        poll_interval = bootstrap.env_float("COOLDOWN_POLL_INTERVAL_SEC", "60")
        scheduler = CooldownScheduler(registry, health_checker, poll_interval=poll_interval)
        cooldown_task = asyncio.create_task(
            scheduler.run(shutdown_event), name="cooldown-scheduler"
        )

    periodic_health_task: "asyncio.Task | None" = None
    if os.getenv("PERIODIC_HEALTH_CHECK_ENABLED", "0").lower() in ("1", "true", "yes"):
        from tg_pool.accounts.periodic_health_scheduler import PeriodicHealthScheduler
        periodic_interval = bootstrap.env_float("PERIODIC_HEALTH_CHECK_INTERVAL_SEC", "1800")
        periodic_scheduler = PeriodicHealthScheduler(
            primary, registry, health_checker, poll_interval=periodic_interval
        )
        periodic_health_task = asyncio.create_task(
            periodic_scheduler.run(shutdown_event), name="periodic-health-scheduler"
        )

    payload = build_payload()
    # Shared by the rate limiter and the warm-up ramp instead of opening two Redis connections.
    redis_client = bootstrap.build_redis_client()
    rate_limiter = build_rate_limiter(redis_client)
    use_monitor = os.getenv("MONITOR_ENABLED", "1").lower() in ("1", "true", "yes")

    warmup_policy = build_warmup_policy()
    warmup_redis_client = redis_client if warmup_policy is not None else None
    auto_responder = build_auto_responder()

    messages_per_account_max_raw = os.getenv("CAMPAIGN_MESSAGES_PER_ACCOUNT_MAX", "").strip()
    messages_per_account_max = int(messages_per_account_max_raw) if messages_per_account_max_raw else None

    exact_total_target_raw = os.getenv("CAMPAIGN_EXACT_TOTAL_TARGET", "").strip()
    exact_total_target = int(exact_total_target_raw) if exact_total_target_raw else None

    worker_batch_size_raw = os.getenv("CAMPAIGN_WORKER_BATCH_SIZE", "").strip()
    worker_batch_size = int(worker_batch_size_raw) if worker_batch_size_raw else None

    repeat_every_hours_raw = os.getenv("CAMPAIGN_REPEAT_EVERY_HOURS", "").strip()
    repeat_every_hours = float(repeat_every_hours_raw) if repeat_every_hours_raw else None

    async def _run_campaign():
        common_kwargs = dict(
            accounts=primary,
            entity_identifiers=[target],
            payload=payload,
            policy=policy,
            rate_limiter=rate_limiter,
            spare_accounts=spares or None,
            event_bus=event_bus,
            shutdown_event=shutdown_event,
            session_encryption_key=session_encryption_key,
            registry=registry,
            warmup_policy=warmup_policy,
            redis_client=warmup_redis_client,
            auto_responder=auto_responder,
            messages_per_account_min=bootstrap.env_int("CAMPAIGN_MESSAGES_PER_ACCOUNT_MIN", "1"),
            messages_per_account_max=messages_per_account_max,
            worker_batch_size=worker_batch_size,
            worker_batch_delay_sec=bootstrap.env_float("CAMPAIGN_WORKER_BATCH_DELAY_SEC", "0"),
        )
        if exact_total_target is not None:
            return await orchestrate_until_target(exact_total_target=exact_total_target, **common_kwargs)
        return await orchestrate_multi_source(**common_kwargs)

    if use_monitor:
        monitor = LiveMonitor()
        monitor.subscribe_to(event_bus)
        async with monitor:
            report = await run_with_repeat(_run_campaign, shutdown_event, repeat_every_hours)
    else:
        report = await run_with_repeat(_run_campaign, shutdown_event, repeat_every_hours)

    was_interrupted = shutdown_event.is_set()

    if cooldown_task is not None or periodic_health_task is not None:
        shutdown_event.set()  # stop background schedulers even if the pipeline finished on its own
        if cooldown_task is not None:
            await cooldown_task
        if periodic_health_task is not None:
            await periodic_health_task

    # Drains the registry's background writer so the final account-state batch isn't lost on exit.
    await registry.close()

    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:
            logger.warning("Failed to close Redis client cleanly.", exc_info=True)

    print("\n" + "=" * 60)
    if was_interrupted:
        print("  [INTERRUPTED — partial report]")
    print(f"  Успешно : {report.succeeded}/{report.total}")
    print(f"  Упало   : {report.failed}")
    if report.per_account:
        print("\n  По аккаунтам:")
        for phone, count in sorted(report.per_account.items()):
            print(f"    {phone}: {count}")
    if report.errors:
        print(f"\n  Ошибки (первые 15 из {len(report.errors)}):")
        for username, error in list(report.errors.items())[:15]:
            print(f"    {username}: {error}")
    print("=" * 60)
