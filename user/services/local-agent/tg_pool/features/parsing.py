"""
tg_pool/features/parsing.py — Standalone user collection / parsing (MODE=parse).

Collects users from one or more Telegram sources (group members, channel
comments, messages, reactions, polls, joins, forum topics), optionally
filters them, and exports to Excel -- independent of any messaging campaign.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional

import tg_pool.bootstrap as bootstrap
from tg_pool.config import AccountConfig, TimingPolicy


def build_parsing_strategy():
    """
    Builds the BaseParsingStrategy selected by PARSE_STRATEGY.
    Defaults to GroupMembersStrategy when unset.
    """
    from tg_pool.extraction.data_extraction import (
        ChannelCommentsStrategy,
        GroupMembersStrategy,
        GroupMessagesStrategy,
        PollsStrategy,
        ReactionsStrategy,
        SystemMessagesStrategy,
        TopicMessagesStrategy,
    )
    name = os.getenv("PARSE_STRATEGY", "members").strip().lower()
    strategies = {
        "members": GroupMembersStrategy,
        "comments": ChannelCommentsStrategy,
        "messages": GroupMessagesStrategy,
        "reactions": ReactionsStrategy,
        "polls": PollsStrategy,
        "system": SystemMessagesStrategy,
    }
    if name == "topic":
        topic_id = bootstrap.env_int("PARSE_TOPIC_ID", "0")
        if not topic_id:
            raise ValueError("PARSE_STRATEGY=topic requires PARSE_TOPIC_ID to be set.")
        return TopicMessagesStrategy(topic_id=topic_id)
    if name not in strategies:
        raise ValueError(f"Unknown PARSE_STRATEGY={name!r}")
    return strategies[name]()


def build_user_filter_pipeline():
    """
    Builds a UserFilterPipeline from PARSE_FILTER_* env vars.
    Filters not set are simply omitted (empty pipeline passes everyone).
    """
    from tg_pool.extraction.user_filter import (
        GenderFilter,
        HasAvatarFilter,
        IsBotFilter,
        IsPremiumFilter,
        LastSeenFilter,
        UserFilterPipeline,
    )
    filters = []

    last_seen_days = os.getenv("PARSE_FILTER_LAST_SEEN_DAYS", "")
    if last_seen_days:
        filters.append(LastSeenFilter(days=bootstrap.parse_int(last_seen_days, "PARSE_FILTER_LAST_SEEN_DAYS")))

    gender = os.getenv("PARSE_FILTER_GENDER", "")
    if gender:
        filters.append(GenderFilter(gender))

    if os.getenv("PARSE_FILTER_HAS_AVATAR", "0").lower() in ("1", "true", "yes"):
        filters.append(HasAvatarFilter())

    if os.getenv("PARSE_FILTER_PREMIUM", "0").lower() in ("1", "true", "yes"):
        filters.append(IsPremiumFilter())

    if os.getenv("PARSE_FILTER_EXCLUDE_BOTS", "1").lower() in ("1", "true", "yes"):
        filters.append(IsBotFilter(is_bot=False))

    return UserFilterPipeline(filters)


async def _proxy_preflight(accounts: List[AccountConfig], logger: logging.Logger) -> List[AccountConfig]:
    """
    Optional PROXY_PREFLIGHT_CHECK_ENABLED gate: checks each account's
    attached proxy before Phase 0 burns time connecting through a dead one.
    PROXY_PREFLIGHT_STRICT additionally excludes accounts with a dead proxy
    instead of just warning about them.
    """
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


def build_job_key() -> Optional[str]:
    """PARSE_JOB_KEY, or None to let orchestrate_extraction_only() derive one from the sources."""
    return os.getenv("PARSE_JOB_KEY", "").strip() or None


async def run(shutdown_event, logger: logging.Logger) -> None:
    from tg_pool.orchestrator import orchestrate_extraction_only

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

    raw_entities = os.getenv("PARSE_ENTITIES", "").strip()
    entities = (
        [e.strip() for e in raw_entities.split(",") if e.strip()]
        if raw_entities
        else [os.getenv("TG_TARGET_ENTITY", "").strip()]
    )
    if not entities[0]:
        logger.error("PARSE_ENTITIES или TG_TARGET_ENTITY не заданы.")
        return

    session_encryption_key = bootstrap.build_session_encryption_key(logger)
    policy = TimingPolicy(
        base_delay_sec=bootstrap.env_float("DELAY_BASE", "2.0"),
        jitter_sec=bootstrap.env_float("DELAY_JITTER", "1.5"),
        max_flood_retries=bootstrap.env_int("MAX_RETRIES", "5"),
    )

    redis_dedup_enabled = os.getenv("PARSE_REDIS_DEDUP_ENABLED", "0").lower() in ("1", "true", "yes")
    redis_client = bootstrap.build_redis_client() if redis_dedup_enabled else None

    exporter = await orchestrate_extraction_only(
        accounts=primary,
        entity_identifiers=entities,
        strategy=build_parsing_strategy(),
        user_filter=build_user_filter_pipeline(),
        policy=policy,
        spare_accounts=spares,
        shutdown_event=shutdown_event,
        session_encryption_key=session_encryption_key,
        redis_client=redis_client,
        job_key=build_job_key(),
    )

    mode = os.getenv("PARSE_EXPORT_MODE", "full").strip().lower()
    export_path = os.getenv("PARSE_EXPORT_PATH", "").strip()

    if mode == "summary":
        path = Path(export_path or "exports/parsed_summary.xlsx")
        exporter.export_summary(path)
        logger.info("Парсинг завершён: %d пользователей → %s", exporter.total, path)
    elif mode == "by_source":
        out_dir = Path(export_path or "exports/by_source")
        result = exporter.export_by_source(out_dir)
        logger.info(
            "Парсинг завершён: %d пользователей, %d файлов → %s",
            exporter.total, len(result), out_dir,
        )
    else:
        path = Path(export_path or "exports/parsed_full.xlsx")
        exporter.export_full(path)
        logger.info(
            "Парсинг завершён: %d пользователей, %d источников → %s",
            exporter.total, len(exporter.sources), path,
        )

    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:
            logger.warning("Failed to close Redis client cleanly.", exc_info=True)
