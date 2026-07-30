"""
src/api/engagement.py — Mass reactions, view-boosting, poll-vote-boosting, and
auto-comments on a single Telegram post, spread across the account pool.

Unlike send_by_id/send_by_numbers (many recipients per sender), an engagement
job has ONE target post and each participating account performs the action
exactly once against it -- that mirrors how Telegram reactions/views/poll
votes actually work (one per account per target; a second call just overwrites
the first, it doesn't add another). "Smart limits" here is three independent,
each-optional layers, all degrading gracefully if their backing service isn't
configured:
  - streams: bounded concurrency across participating accounts (asyncio.Semaphore)
  - delay_min_sec/delay_max_sec: per-account startup stagger, so N accounts
    don't all hit Telegram in the same instant
  - a per-account, per-action-type daily cap via Redis (RedisRateLimiter --
    the same token-bucket primitive src/messaging uses for warm-up caps),
    skipped entirely if REDIS_URL isn't configured, same opt-in pattern as
    DATABASE_URL/LICENSE_SERVER_URL elsewhere in this app
Plus the existing auto_stop_ban/spamblock/floodwait convention shared with
every other job manager in this file's family (send_by_id, invite_by_number, ...).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    PeerFloodError,
    UserDeactivatedBanError,
)
from telethon.tl.functions.messages import GetMessagesViewsRequest, SendReactionRequest
from telethon.tl.types import ReactionEmoji

from src.accounts.connection_manager import ClientFactory
from src.accounts.proxy_safety import ensure_all_proxied, unproxied_phones
from src.api.pool_guard import PoolAccessGuard, PoolBusyError
from src.config import AccountConfig
from src.messaging.messaging_service import render_template
from src.messaging.spintax import resolve_spintax

logger = logging.getLogger(__name__)

ACTION_TYPES = ("reaction", "view", "poll_vote", "comment")

# Conservative platform-aware defaults for the per-account daily cap (Redis-backed,
# only enforced when REDIS_URL is configured). Views in particular: Telegram's own
# view-increment call only registers a small handful of times per account per day
# regardless of how many messages you target it at (Telethon's "Increasing View
# Count" wiki: "This can only be done once or twice per day per account"), so its
# default sits far below the others.
DEFAULT_DAILY_CAPS: Dict[str, int] = {
    "reaction": 80,
    "view": 15,
    "poll_vote": 20,
    "comment": 30,
}


class EngagementAlreadyRunningError(RuntimeError):
    """Raised when another engagement job already owns the account pool."""


@dataclass
class EngagementResultRow:
    account_phone: str
    state: str = "pending"
    message: str = ""


@dataclass(frozen=True)
class EngagementOptions:
    action_type: str
    target_chat: str
    target_message_id: int
    reaction_emoji: str
    poll_option_index: Optional[int]
    comment_text: str
    streams: int
    delay_min_sec: float
    delay_max_sec: float
    max_flood_wait_sec: float
    daily_cap_per_account: int
    auto_stop_ban: int
    auto_stop_spamblock: int
    auto_stop_floodwait: int
    results_dir: str


@dataclass
class _Run:
    job_id: str
    action_type: str
    shutdown_event: asyncio.Event
    results: List[EngagementResultRow] = field(default_factory=list)
    task: Optional[asyncio.Task] = None
    succeeded: int = 0
    failed: int = 0
    skipped_daily_cap: int = 0
    finished: bool = False
    error: Optional[str] = None
    ban_count: int = 0
    spamblock_count: int = 0
    floodwait_count: int = 0
    unproxied_senders: List[str] = field(default_factory=list)
    export_path: Optional[str] = None


class EngagementManager:
    """Owns one cancellable reactions/views/poll-votes/comments job."""

    def __init__(
        self,
        accounts: List[AccountConfig],
        pool_guard: PoolAccessGuard,
        session_encryption_key: Optional[bytes] = None,
        redis_client: Optional[Any] = None,
        proxy_repository: Optional[Any] = None,
    ) -> None:
        self._accounts_by_phone = {self._phone_key(a.phone): a for a in accounts}
        self._pool_guard = pool_guard
        self._session_encryption_key = session_encryption_key
        self._redis_client = redis_client
        self._proxy_repository = proxy_repository
        self._run: Optional[_Run] = None

    @staticmethod
    def _phone_key(phone: str) -> str:
        return re.sub(r"[^0-9]", "", phone or "")

    def register_account(self, account: AccountConfig) -> None:
        self._accounts_by_phone[self._phone_key(account.phone)] = account

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def start(
        self,
        *,
        action_type: str,
        target_chat: str,
        target_message_id: int,
        reaction_emoji: str = "",
        poll_option_index: Optional[int] = None,
        comment_text: str = "",
        sender_phones: Optional[List[str]] = None,
        streams: int = 1,
        delay_min_sec: float = 1.0,
        delay_max_sec: float = 8.0,
        max_flood_wait_sec: float = 120.0,
        daily_cap_per_account: Optional[int] = None,
        max_total_accounts: Optional[int] = None,
        auto_stop_ban: int = 0,
        auto_stop_spamblock: int = 0,
        auto_stop_floodwait: int = 0,
        require_proxy: bool = False,
        results_dir: str = "exports",
    ) -> str:
        if self.is_running:
            raise EngagementAlreadyRunningError("An engagement job is already running.")
        if action_type not in ACTION_TYPES:
            raise ValueError(f"Unknown action_type: {action_type!r}")
        if not target_chat.strip():
            raise ValueError("target_chat is required.")
        if target_message_id <= 0:
            raise ValueError("target_message_id must be a positive message ID.")
        if action_type == "reaction" and not reaction_emoji.strip():
            raise ValueError("reaction_emoji is required for the reaction action.")
        if action_type == "poll_vote" and (poll_option_index is None or poll_option_index < 0):
            raise ValueError("poll_option_index is required for the poll_vote action.")
        if action_type == "comment" and not comment_text.strip():
            raise ValueError("comment_text is required for the comment action.")

        senders = self._normalize_senders(sender_phones)
        if not senders:
            raise ValueError("No valid sender accounts available.")
        if max_total_accounts is not None and max_total_accounts > 0:
            senders = senders[: int(max_total_accounts)]

        sender_accounts = [self._accounts_by_phone[self._phone_key(p)] for p in senders]
        if require_proxy:
            ensure_all_proxied(sender_accounts)
        unproxied = unproxied_phones(sender_accounts)

        delay_min = max(0.0, float(delay_min_sec))
        delay_max = max(delay_min, float(delay_max_sec))
        stream_count = max(1, min(int(streams), len(senders)))
        cap = int(daily_cap_per_account) if daily_cap_per_account else DEFAULT_DAILY_CAPS[action_type]

        try:
            self._pool_guard.try_acquire("engagement")
        except PoolBusyError as exc:
            raise EngagementAlreadyRunningError(str(exc)) from exc

        options = EngagementOptions(
            action_type=action_type,
            target_chat=target_chat.strip(),
            target_message_id=int(target_message_id),
            reaction_emoji=reaction_emoji.strip(),
            poll_option_index=poll_option_index,
            comment_text=comment_text,
            streams=stream_count,
            delay_min_sec=delay_min,
            delay_max_sec=delay_max,
            max_flood_wait_sec=max(0.0, float(max_flood_wait_sec)),
            daily_cap_per_account=max(0, cap),
            auto_stop_ban=max(0, int(auto_stop_ban)),
            auto_stop_spamblock=max(0, int(auto_stop_spamblock)),
            auto_stop_floodwait=max(0, int(auto_stop_floodwait)),
            results_dir=results_dir or "exports",
        )
        job_id = uuid.uuid4().hex[:12]
        run = _Run(
            job_id=job_id,
            action_type=action_type,
            shutdown_event=asyncio.Event(),
            results=[EngagementResultRow(account_phone=phone) for phone in senders],
            unproxied_senders=unproxied,
        )

        async def _runner() -> None:
            try:
                await self._run_all(run, senders, options)
            except Exception as exc:
                logger.exception("Engagement job %s failed", job_id)
                run.error = str(exc)
            finally:
                try:
                    run.export_path = self._export_results(run, options.results_dir)
                except Exception as exc:
                    logger.exception("Could not export engagement results")
                    run.error = run.error or f"Result export failed: {exc}"
                run.finished = True
                self._pool_guard.release("engagement")

        run.task = asyncio.create_task(_runner(), name=f"api-engagement-{job_id}")
        self._run = run
        return job_id

    def _normalize_senders(self, sender_phones: Optional[List[str]]) -> List[str]:
        source = sender_phones or [account.phone for account in self._accounts_by_phone.values()]
        result: List[str] = []
        seen: set[str] = set()
        for phone in source:
            key = self._phone_key(phone)
            if not key or key in seen:
                continue
            if key not in self._accounts_by_phone:
                raise ValueError(f"Sender account not found: {phone}")
            seen.add(key)
            result.append(self._accounts_by_phone[key].phone)
        return result

    async def stop(self) -> None:
        if self._run is None or self._run.task is None:
            return
        self._run.shutdown_event.set()
        await self._run.task

    def status(self) -> dict:
        if self._run is None:
            return {"running": False}
        run = self._run
        return {
            "running": not run.finished,
            "job_id": run.job_id,
            "action_type": run.action_type,
            "total": len(run.results),
            "succeeded": run.succeeded,
            "failed": run.failed,
            "skipped_daily_cap": run.skipped_daily_cap,
            "finished": run.finished,
            "error": run.error,
            "ban_count": run.ban_count,
            "spamblock_count": run.spamblock_count,
            "floodwait_count": run.floodwait_count,
            "unproxied_senders": run.unproxied_senders,
            "export_path": run.export_path,
            "results": [
                {"account_phone": row.account_phone, "state": row.state, "message": row.message}
                for row in run.results
            ],
        }

    async def _run_all(self, run: _Run, senders: List[str], options: EngagementOptions) -> None:
        semaphore = asyncio.Semaphore(options.streams)

        async def worker(phone: str, row: EngagementResultRow) -> None:
            async with semaphore:
                if run.shutdown_event.is_set():
                    row.state = "skipped"
                    row.message = "Stopped before start."
                    run.failed += 1
                    return
                try:
                    await asyncio.wait_for(
                        run.shutdown_event.wait(),
                        timeout=random.uniform(options.delay_min_sec, options.delay_max_sec),
                    )
                    row.state = "skipped"
                    row.message = "Stopped during stagger delay."
                    run.failed += 1
                    return
                except asyncio.TimeoutError:
                    pass
                await self._perform_one(run, phone, row, options)

        await asyncio.gather(*(worker(phone, row) for phone, row in zip(senders, run.results)))

    async def _perform_one(
        self, run: _Run, phone: str, row: EngagementResultRow, options: EngagementOptions
    ) -> None:
        if self._redis_client is not None and options.daily_cap_per_account > 0:
            allowed = await self._check_daily_cap(phone, options)
            if not allowed:
                row.state = "skipped"
                row.message = "Daily cap for this account reached."
                run.skipped_daily_cap += 1
                return

        client = None
        try:
            client = await self._connect(phone)
            await self._attempt_with_flood_wait(run, client, row, options)
        except (UserDeactivatedBanError, AuthKeyUnregisteredError) as exc:
            run.ban_count += 1
            row.state = "failed"
            row.message = f"Sender banned or unauthorized: {type(exc).__name__}"
            run.failed += 1
            self._auto_stop_reached(run, options)
            await self._record_ban_signal(phone)
        except PeerFloodError as exc:
            run.spamblock_count += 1
            row.state = "failed"
            row.message = f"Sender spam-blocked: {type(exc).__name__}"
            run.failed += 1
            self._auto_stop_reached(run, options)
            await self._record_ban_signal(phone)
        except Exception as exc:
            row.state = "failed"
            row.message = f"{type(exc).__name__}: {exc}"
            run.failed += 1
            logger.warning("Engagement action failed for %s: %s", phone, exc)
        finally:
            if client is not None:
                await self._disconnect(phone, client)

    async def _attempt_with_flood_wait(
        self, run: _Run, client, row: EngagementResultRow, options: EngagementOptions
    ) -> None:
        while True:
            try:
                await self._perform_action(client, options)
                row.state = "done"
                row.message = "OK"
                run.succeeded += 1
                return
            except FloodWaitError as exc:
                run.floodwait_count += 1
                if self._auto_stop_reached(run, options) or exc.seconds > options.max_flood_wait_sec:
                    row.state = "failed"
                    row.message = f"FloodWait {exc.seconds}s exceeds maximum timeout."
                    run.failed += 1
                    return
                row.state = "waiting"
                row.message = f"FloodWait {exc.seconds}s; resuming automatically."
                try:
                    await asyncio.wait_for(run.shutdown_event.wait(), timeout=float(exc.seconds))
                    row.state = "skipped"
                    row.message = "Stopped during FloodWait."
                    run.failed += 1
                    return
                except asyncio.TimeoutError:
                    pass

    async def _perform_action(self, client, options: EngagementOptions) -> None:
        peer = await client.get_input_entity(options.target_chat)
        if options.action_type == "reaction":
            await client(
                SendReactionRequest(
                    peer=peer,
                    msg_id=options.target_message_id,
                    reaction=[ReactionEmoji(emoticon=options.reaction_emoji)],
                )
            )
        elif options.action_type == "view":
            await client(
                GetMessagesViewsRequest(
                    peer=peer, id=[options.target_message_id], increment=True
                )
            )
        elif options.action_type == "poll_vote":
            message = await client.get_messages(peer, ids=options.target_message_id)
            if message is None or not message.poll:
                raise ValueError("Target message has no poll.")
            await message.click(options.poll_option_index)
        elif options.action_type == "comment":
            text = render_template(resolve_spintax(options.comment_text), {})
            await client.send_message(
                peer, text, comment_to=options.target_message_id, parse_mode="html"
            )

    async def _check_daily_cap(self, phone: str, options: EngagementOptions) -> bool:
        from src.messaging.lua_storage import RedisRateLimiter

        limiter = RedisRateLimiter(
            self._redis_client,
            pool_id=f"engagement:{options.action_type}:{self._phone_key(phone)}",
            capacity=options.daily_cap_per_account,
            refill_rate=options.daily_cap_per_account / 86400.0,
        )
        allowed, _reason = await limiter.check_and_consume(phone)
        return allowed

    async def _record_ban_signal(self, phone: str) -> None:
        """
        Flags the sender's proxy (if any and if proxy tracking is configured)
        as having seen a ban/spamblock signal -- a proxy can answer connectivity
        checks fine while still being a burned exit IP that Telegram is banning
        every account through, which plain liveness checks never catch.
        """
        if self._proxy_repository is None:
            return
        account = self._accounts_by_phone.get(self._phone_key(phone))
        if account is None or account.proxy is None:
            return
        try:
            await self._proxy_repository.record_ban_signal(
                proxy_type=account.proxy.proxy_type,
                host=account.proxy.host,
                port=account.proxy.port,
                username=account.proxy.username or "",
            )
        except Exception:
            logger.debug("Could not record ban signal for proxy of %s", phone, exc_info=True)

    def _auto_stop_reached(self, run: _Run, options: EngagementOptions) -> bool:
        reached = (
            (options.auto_stop_ban > 0 and run.ban_count >= options.auto_stop_ban)
            or (
                options.auto_stop_spamblock > 0
                and run.spamblock_count >= options.auto_stop_spamblock
            )
            or (
                options.auto_stop_floodwait > 0
                and run.floodwait_count >= options.auto_stop_floodwait
            )
        )
        if reached:
            run.shutdown_event.set()
        return reached

    async def _connect(self, phone: str):
        account = self._accounts_by_phone.get(self._phone_key(phone))
        if account is None:
            raise ValueError(f"Sender account not found: {phone}")
        if self._session_encryption_key is not None:
            from src.accounts.session_crypto import ensure_decrypted

            ensure_decrypted(account.session_path, self._session_encryption_key)
        client = ClientFactory.build(account)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise PermissionError(f"Session for {phone} is not authorized.")
        return client

    async def _disconnect(self, phone: str, client) -> None:
        try:
            if client.is_connected():
                await client.disconnect()
        finally:
            account = self._accounts_by_phone.get(self._phone_key(phone))
            if account is not None and self._session_encryption_key is not None:
                from src.accounts.session_crypto import ensure_encrypted

                ensure_encrypted(account.session_path, self._session_encryption_key)

    @staticmethod
    def _export_results(run: _Run, results_dir: str) -> str:
        output_dir = Path(results_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"engagement-{run.action_type}-{run.job_id}.xlsx"
        pd.DataFrame(
            [
                {"Account": row.account_phone, "Status": row.state, "Details": row.message}
                for row in run.results
            ]
        ).to_excel(path, index=False)
        return str(path.resolve())
