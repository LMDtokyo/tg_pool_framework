"""
src/health_checker.py — Autonomous pool health checker (extended).

Status taxonomy:
  ALIVE      — authorized, no restrictions detected.
  BANNED     — hard ban: UserDeactivatedBanError or AuthKeyUnregisteredError.
  SPAMBLOCK  — @SpamBot reports active (possibly temporary) restrictions.
  FROZEN     — @SpamBot indicates account is frozen (complete freeze, not spam).
  FLOOD      — currently throttled by Telegram (FloodWaitError).
  PROXY_DEAD — proxy unreachable or connection failure.
  UNKNOWN    — cannot determine status (unexpected error).

Deep-check strategy:
  1. connect() + is_user_authorized() — fast auth check.
  2. get_me() — extract premium flag, username, first_name.
  3. GetStateRequest() — lightweight RPC; fails on hard bans.
  4. @SpamBot check (deep_check=True) — sends /start, parses reply for:
       a) Restriction date (temporary spamblock with expiry).
       b) "Frozen" keywords → FROZEN status.
       c) Clean phrases → ALIVE.

Date parsing:
  _parse_restriction_date() understands:
    "until January 15, 2024"   "until 15 January 2024"
    "до 15 января 2024"         "until 2024-01-15"   "до 15.01.2024"

AccountState (frozen dataclass):
  Rich summary of a single account's state — used by AccountRegistry.
  Generated on-demand via HealthResult.account_state property.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Awaitable, Callable, Dict, List, Optional

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    UserDeactivatedBanError,
    UserDeactivatedError,
)
from telethon.tl.functions.account import GetPasswordRequest
from telethon.tl.functions.updates import GetStateRequest

from src.config import AccountConfig, TimingPolicy
from src.accounts.connection_manager import ClientFactory
from src.accounts.geo import country_for_phone
from src.monitoring.event_bus import AccountStatusEvent, EventBus

logger = logging.getLogger(__name__)

_SPAMBOT_CLEAN_PHRASES = (
    "ограничения не наложены",
    "no limits are currently imposed",
    "free from any restrictions",
    "good news",
)
_SPAMBOT_FROZEN_PHRASES = (
    "frozen",
    "заморожен",
    "заморожена",
    "account is frozen",
)
_SPAMBOT_USERNAME = "SpamBot"
_SPAMBOT_REPLY_TIMEOUT = 15.0
_SESSION_LOCK_RETRY_ATTEMPTS = 4
_SESSION_LOCK_RETRY_DELAY_SEC = 5.0


# ---------------------------------------------------------------------------
# Russian / English month tables for date parsing
# ---------------------------------------------------------------------------

_RU_MONTHS: Dict[str, int] = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

_EN_MONTHS: Dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _parse_restriction_date(text: str) -> Optional[datetime]:
    """
    Extract restriction end-date from SpamBot reply text.

    Handles:
      "until January 15, 2024"  — English, month-first
      "until 15 January 2024"   — English, day-first
      "до 15 января 2024"        — Russian
      "until 2024-01-15"         — ISO-8601
      "до 15.01.2024"            — Russian dot-notation

    Returns a timezone-aware UTC datetime, or None if no date is found.
    """
    # EN: "until MonthName Day Year"
    m = re.search(r"until\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text, re.IGNORECASE)
    if m:
        month = _EN_MONTHS.get(m.group(1).lower())
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(2)), tzinfo=timezone.utc)
            except ValueError:
                pass

    # EN: "until Day MonthName Year"
    m = re.search(r"until\s+(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})", text, re.IGNORECASE)
    if m:
        month = _EN_MONTHS.get(m.group(2).lower())
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(1)), tzinfo=timezone.utc)
            except ValueError:
                pass

    # RU: "до DD Month YYYY"
    m = re.search(r"до\s+(\d{1,2})\s+([А-Яа-яёЁ]+)\s+(\d{4})", text, re.IGNORECASE)
    if m:
        month = _RU_MONTHS.get(m.group(2).lower())
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(1)), tzinfo=timezone.utc)
            except ValueError:
                pass

    # ISO: "until 2024-01-15"
    m = re.search(r"until\s+(\d{4})-(\d{2})-(\d{2})", text, re.IGNORECASE)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass

    # RU dot: "до 15.01.2024" or "до 15/01/2024"
    m = re.search(r"до\s+(\d{2})[./](\d{2})[./](\d{4})", text, re.IGNORECASE)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def _is_database_locked(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "database is locked" in str(exc).lower()


# ---------------------------------------------------------------------------
# Enums and dataclasses
# ---------------------------------------------------------------------------

class AccountStatus(str, Enum):
    ALIVE      = "alive"
    BANNED     = "banned"
    UNAUTHORIZED = "unauthorized"
    SPAMBLOCK  = "spamblock"
    FROZEN     = "frozen"
    FLOOD      = "flood"
    PROXY_DEAD = "proxy_dead"
    UNKNOWN    = "unknown"


@dataclass(frozen=True)
class AccountState:
    """
    Rich, immutable snapshot of a single account's state.

    Produced from HealthResult.account_state and stored in AccountRegistry.
    """
    status: AccountStatus
    is_premium: bool = False
    restriction_expires: Optional[datetime] = None
    error_message: Optional[str] = None
    username: str = ""
    first_name: str = ""
    country: Optional[str] = None
    has_2fa: bool = False


@dataclass
class HealthResult:
    """
    Mutable result of a single account health check.

    Backward-compatible: existing code that only reads `phone`, `status`,
    `detail`, and `flood_wait_seconds` continues to work unchanged.
    New fields (`is_premium`, `restriction_expires`, `username`, `first_name`,
    `country`, `has_2fa`) default to safe zero-values.
    """
    phone: str
    status: AccountStatus
    detail: str = ""
    flood_wait_seconds: int = 0
    is_premium: bool = False
    restriction_expires: Optional[datetime] = None
    username: str = ""
    first_name: str = ""
    country: Optional[str] = None
    has_2fa: bool = False

    @property
    def is_usable(self) -> bool:
        return self.status == AccountStatus.ALIVE

    @property
    def account_state(self) -> AccountState:
        """Convert to the immutable AccountState used by AccountRegistry."""
        return AccountState(
            status=self.status,
            is_premium=self.is_premium,
            restriction_expires=self.restriction_expires,
            error_message=self.detail or None,
            username=self.username,
            first_name=self.first_name,
            country=self.country,
            has_2fa=self.has_2fa,
        )


@dataclass
class PoolHealthReport:
    results: List[HealthResult] = field(default_factory=list)

    @property
    def alive(self) -> List[HealthResult]:
        return [r for r in self.results if r.status == AccountStatus.ALIVE]

    @property
    def banned(self) -> List[HealthResult]:
        return [r for r in self.results if r.status == AccountStatus.BANNED]

    @property
    def unauthorized(self) -> List[HealthResult]:
        return [r for r in self.results if r.status == AccountStatus.UNAUTHORIZED]

    @property
    def spamblocked(self) -> List[HealthResult]:
        return [r for r in self.results if r.status == AccountStatus.SPAMBLOCK]

    @property
    def frozen(self) -> List[HealthResult]:
        return [r for r in self.results if r.status == AccountStatus.FROZEN]

    @property
    def flooded(self) -> List[HealthResult]:
        return [r for r in self.results if r.status == AccountStatus.FLOOD]

    def summary(self) -> str:
        return (
            f"PoolHealth: total={len(self.results)} "
            f"alive={len(self.alive)} "
            f"banned={len(self.banned)} "
            f"unauthorized={len(self.unauthorized)} "
            f"spamblock={len(self.spamblocked)} "
            f"frozen={len(self.frozen)} "
            f"flood={len(self.flooded)}"
        )


# ---------------------------------------------------------------------------
# HealthChecker
# ---------------------------------------------------------------------------

class HealthChecker:
    """
    Parallel pool health checker with premium detection and spamblock date parsing.

    Usage:
        checker = HealthChecker(policy=TimingPolicy(), event_bus=bus)
        report = await checker.check_pool_health(accounts, deep_check=True)
        for result in report.results:
            print(result.phone, result.status, result.is_premium,
                  result.restriction_expires)
    """

    def __init__(
        self,
        policy: Optional[TimingPolicy] = None,
        concurrency: int = 5,
        event_bus: Optional[EventBus] = None,
        account_timeout_sec: float = 90.0,
    ) -> None:
        self._policy = policy or TimingPolicy()
        self._sem = asyncio.Semaphore(concurrency)
        self._event_bus = event_bus
        self._account_timeout_sec = account_timeout_sec

    async def check_pool_health(
        self,
        accounts: List[AccountConfig],
        deep_check: bool = False,
        on_result: Optional[Callable[[HealthResult], Awaitable[None]]] = None,
    ) -> PoolHealthReport:
        logger.info(
            "Starting health check: %d accounts, deep_check=%s",
            len(accounts), deep_check,
        )

        report = PoolHealthReport()
        tasks = [
            asyncio.create_task(self._check_one_bounded(account, deep_check=deep_check))
            for account in accounts
        ]

        for completed in asyncio.as_completed(tasks):
            account, result = await completed
            if isinstance(result, Exception):
                logger.error(
                    "Health check raised unexpectedly for %s: %s",
                    account.phone, result,
                )
                result = HealthResult(
                    phone=account.phone,
                    status=AccountStatus.UNKNOWN,
                    detail=f"Unexpected: {result}",
                    country=country_for_phone(account.phone),
                )
            report.results.append(result)
            if on_result is not None:
                try:
                    await on_result(result)
                except Exception:
                    logger.exception("Failed to handle health result for %s", result.phone)

        logger.info(report.summary())
        return report

    async def _check_one_bounded(
        self,
        account: AccountConfig,
        deep_check: bool,
    ) -> tuple[AccountConfig, HealthResult | Exception]:
        try:
            result = await asyncio.wait_for(
                self._check_one(account, deep_check=deep_check),
                timeout=self._account_timeout_sec,
            )
            return account, result
        except asyncio.TimeoutError:
            result = HealthResult(
                phone=account.phone,
                status=AccountStatus.UNKNOWN,
                detail=f"Health check timed out after {self._account_timeout_sec:.0f}s.",
                country=country_for_phone(account.phone),
            )
            await self._publish(result)
            return account, result
        except Exception as exc:
            return account, exc

    async def _check_one(
        self,
        account: AccountConfig,
        deep_check: bool,
    ) -> HealthResult:
        async with self._sem:
            return await self._run_checks_with_retries(account, deep_check)

    async def _run_checks_with_retries(
        self,
        account: AccountConfig,
        deep_check: bool,
    ) -> HealthResult:
        for attempt in range(1, _SESSION_LOCK_RETRY_ATTEMPTS + 1):
            try:
                return await self._run_checks(account, deep_check)
            except sqlite3.OperationalError as exc:
                if not _is_database_locked(exc) or attempt == _SESSION_LOCK_RETRY_ATTEMPTS:
                    raise
                logger.warning(
                    "Session database locked for %s; retrying in %.1fs (%d/%d).",
                    account.phone,
                    _SESSION_LOCK_RETRY_DELAY_SEC,
                    attempt,
                    _SESSION_LOCK_RETRY_ATTEMPTS,
                )
                await asyncio.sleep(_SESSION_LOCK_RETRY_DELAY_SEC)

        raise RuntimeError("unreachable health-check retry state")

    async def _run_checks(
        self,
        account: AccountConfig,
        deep_check: bool,
    ) -> HealthResult:
        client = ClientFactory.build(account)
        is_premium = False
        username = ""
        first_name = ""
        has_2fa = False
        # Phone-derived, offline, always known regardless of how far the check gets.
        country = country_for_phone(account.phone)

        try:
            try:
                await client.connect()
            except (OSError, ConnectionError) as exc:
                result = HealthResult(
                    phone=account.phone,
                    status=AccountStatus.PROXY_DEAD,
                    detail=f"Connection failed: {exc}",
                    country=country,
                )
                await self._publish(result)
                return result

            if not await client.is_user_authorized():
                result = HealthResult(
                    phone=account.phone,
                    status=AccountStatus.UNAUTHORIZED,
                    detail="Session not authorized (expired or deauthorized).",
                    country=country,
                )
                await self._publish(result)
                return result

            # --- Premium + profile info ---
            try:
                me = await client.get_me()
                if me is not None:
                    # Use `is True` to guard against MagicMock in tests
                    is_premium = getattr(me, "premium", None) is True
                    username = str(getattr(me, "username", "") or "")
                    first_name = str(getattr(me, "first_name", "") or "")
            except Exception as exc:
                logger.debug("get_me() failed for %s: %s", account.phone, exc)

            # --- 2FA (two-step verification) presence ---
            try:
                password_info = await client(GetPasswordRequest())
                has_2fa = bool(getattr(password_info, "has_password", False))
            except Exception as exc:
                logger.debug("GetPasswordRequest failed for %s: %s", account.phone, exc)

            # --- Lightweight API liveness check ---
            try:
                await client(GetStateRequest())
            except (UserDeactivatedBanError, UserDeactivatedError) as exc:
                result = HealthResult(
                    phone=account.phone,
                    status=AccountStatus.BANNED,
                    detail=f"Hard ban: {type(exc).__name__}",
                    country=country,
                    has_2fa=has_2fa,
                )
                await self._publish(result)
                return result
            except AuthKeyUnregisteredError as exc:
                result = HealthResult(
                    phone=account.phone,
                    status=AccountStatus.BANNED,
                    detail=f"Auth key revoked: {exc}",
                    country=country,
                    has_2fa=has_2fa,
                )
                await self._publish(result)
                return result
            except FloodWaitError as exc:
                result = HealthResult(
                    phone=account.phone,
                    status=AccountStatus.FLOOD,
                    detail=f"FloodWait {exc.seconds}s on GetStateRequest",
                    flood_wait_seconds=exc.seconds,
                    country=country,
                    has_2fa=has_2fa,
                )
                await self._publish(result)
                return result

            # --- SpamBot deep check ---
            if deep_check:
                spambot_result = await self._check_spambot(client, account.phone)
                if spambot_result is not None:
                    # Enrich spambot result with profile fields collected above
                    enriched = HealthResult(
                        phone=spambot_result.phone,
                        status=spambot_result.status,
                        detail=spambot_result.detail,
                        flood_wait_seconds=spambot_result.flood_wait_seconds,
                        is_premium=is_premium,
                        restriction_expires=spambot_result.restriction_expires,
                        username=username,
                        first_name=first_name,
                        country=country,
                        has_2fa=has_2fa,
                    )
                    await self._publish(enriched)
                    return enriched

            result = HealthResult(
                phone=account.phone,
                status=AccountStatus.ALIVE,
                detail="All checks passed.",
                is_premium=is_premium,
                username=username,
                first_name=first_name,
                country=country,
                has_2fa=has_2fa,
            )
            await self._publish(result)
            return result

        except Exception as exc:
            if _is_database_locked(exc):
                raise
            logger.warning("Unexpected error checking %s: %s", account.phone, exc)
            result = HealthResult(
                phone=account.phone,
                status=AccountStatus.UNKNOWN,
                detail=str(exc),
                country=country,
            )
            await self._publish(result)
            return result

        finally:
            try:
                disconnected = client.disconnect()
                if inspect.isawaitable(disconnected):
                    await disconnected
            except Exception as exc:
                if _is_database_locked(exc):
                    logger.warning("Session database locked while disconnecting %s: %s", account.phone, exc)
                else:
                    logger.debug("Health-check disconnect failed for %s: %s", account.phone, exc)

    async def _publish(self, result: HealthResult) -> None:
        if self._event_bus is not None:
            await self._event_bus.publish(AccountStatusEvent(
                phone=result.phone,
                status=result.status.value,
                detail=result.detail,
            ))

    async def _check_spambot(
        self,
        client: TelegramClient,
        phone: str,
    ) -> Optional[HealthResult]:
        """
        Contact @SpamBot and parse its reply.

        Returns:
          None          — account is clean (no restriction).
          HealthResult  — restriction detected; status is SPAMBLOCK or FROZEN.
                          restriction_expires is set if a date was found in reply.
        """
        try:
            bot = await client.get_entity(_SPAMBOT_USERNAME)
            await client.send_message(bot, "/start")

            deadline = asyncio.get_event_loop().time() + _SPAMBOT_REPLY_TIMEOUT

            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(2.0)
                messages = await client.get_messages(bot, limit=1)
                if not messages:
                    continue
                last = messages[0]
                if last.out:
                    continue

                text = (last.text or "").lower()
                raw_text = last.text or ""

                if any(phrase in text for phrase in _SPAMBOT_CLEAN_PHRASES):
                    logger.debug("[%s] @SpamBot: no restrictions.", phone)
                    return None

                if any(phrase in text for phrase in _SPAMBOT_FROZEN_PHRASES):
                    logger.warning("[%s] @SpamBot: account FROZEN.", phone)
                    return HealthResult(
                        phone=phone,
                        status=AccountStatus.FROZEN,
                        detail=f"@SpamBot: frozen — {raw_text[:120]}",
                        restriction_expires=_parse_restriction_date(raw_text),
                    )

                if text:
                    expires = _parse_restriction_date(raw_text)
                    logger.warning(
                        "[%s] @SpamBot restriction detected; expires=%s", phone, expires
                    )
                    return HealthResult(
                        phone=phone,
                        status=AccountStatus.SPAMBLOCK,
                        detail=f"@SpamBot reply: {raw_text[:120]}",
                        restriction_expires=expires,
                    )

            logger.warning(
                "[%s] @SpamBot: no reply within %.1fs.", phone, _SPAMBOT_REPLY_TIMEOUT
            )
            return None

        except FloodWaitError as exc:
            logger.warning("[%s] FloodWait contacting @SpamBot: %ds", phone, exc.seconds)
            return HealthResult(
                phone=phone,
                status=AccountStatus.FLOOD,
                detail=f"FloodWait {exc.seconds}s contacting @SpamBot",
                flood_wait_seconds=exc.seconds,
            )
        except Exception as exc:
            logger.warning("[%s] Cannot check @SpamBot: %s", phone, exc)
            return None
