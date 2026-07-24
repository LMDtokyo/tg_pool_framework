"""
src/features/account_check.py — Standalone account health check (MODE=check_accounts).

Loads every configured account (ACCOUNTS_DIR / TG_API_ID_i / TDATA_ACCOUNTS_DIR,
including spares), runs HealthChecker.check_pool_health() against all of them,
persists results to the registry (and the DB, if DATABASE_URL is configured),
and prints a console report -- independent of any messaging campaign or
parsing job.
"""

from __future__ import annotations

import logging
import os

import src.bootstrap as bootstrap
from src.config import TimingPolicy


async def run(shutdown_event, logger: logging.Logger) -> None:
    from src.accounts.account_registry import AccountRegistry
    from src.monitoring.monitor import LiveMonitor

    primary, spares = bootstrap.load_accounts()
    primary = primary + await bootstrap.load_tdata_accounts()
    accounts = primary + spares
    if not accounts:
        logger.error(
            "Аккаунты не найдены. Заполните ACCOUNTS_DIR, TG_API_ID_1/... или "
            "TDATA_ACCOUNTS_DIR в .env"
        )
        return

    logger.info("Проверка здоровья: %d аккаунтов (включая резервные).", len(accounts))

    policy = TimingPolicy()
    db_session_factory = bootstrap.build_db_session_factory()
    registry = AccountRegistry(repository=bootstrap.build_account_repository(db_session_factory))
    await registry.load_from_repository()
    await registry.register_many(accounts)

    health_checker = bootstrap.build_health_checker(policy, event_bus=None)
    deep = os.getenv("ACCOUNT_CHECK_DEEP", "0").lower() in ("1", "true", "yes")

    report = await health_checker.check_pool_health(accounts, deep_check=deep)
    logger.info(report.summary())

    for result in report.results:
        await registry.update_state(result.phone, result.account_state)

    LiveMonitor().print_pool_table(registry.snapshot())

    await registry.close()
