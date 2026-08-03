"""
tg_pool/api/stories.py — Story views/reactions on someone else's story, plus
publishing a story from pool accounts. Same shape as engagement.py: each
participating account performs the action exactly once (view/react a target
story, or publish its own), spread across the pool with the same "smart
limits" -- streams, stagger delay, a Redis-backed per-account daily cap, and
the shared proxy-safety/ban-signal hooks.

Telethon has no high-level convenience methods for stories -- the library is
explicitly "feature-frozen" and stories are only reachable via the raw
functions.stories.* API (per the project's own wiki/docs) -- so this module
talks to ReadStoriesRequest / stories.SendReactionRequest / SendStoryRequest
directly, the same way the wiki's own story examples do.
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
from telethon import helpers
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    PeerFloodError,
    UserDeactivatedBanError,
)
from telethon.tl.functions.stories import (
    ReadStoriesRequest,
    SendReactionRequest as SendStoryReactionRequest,
    SendStoryRequest,
)
from telethon.tl.types import (
    DocumentAttributeVideo,
    InputMediaUploadedDocument,
    InputMediaUploadedPhoto,
    InputPrivacyValueAllowAll,
    InputPrivacyValueAllowContacts,
    ReactionEmoji,
)

from tg_pool.accounts.account_registry import AccountRegistry
from tg_pool.accounts.connection_manager import ClientFactory
from tg_pool.accounts.proxy_safety import ensure_all_proxied, ensure_no_shared_proxies, unproxied_phones
from tg_pool.accounts.warmup_policy import WarmupPolicy, account_age_days
from tg_pool.api.pool_guard import PoolAccessGuard, PoolBusyError
from tg_pool.api.security_utils import scrub_secrets
from tg_pool.config import AccountConfig

logger = logging.getLogger(__name__)

ACTION_TYPES = ("view", "reaction", "post")

# Conservative defaults, same reasoning as engagement.py's DEFAULT_DAILY_CAPS:
# posting several stories a day from one account is a stronger bot signal
# than viewing/reacting, so it gets the tightest default by far.
DEFAULT_DAILY_CAPS: Dict[str, int] = {
    "view": 15,
    "reaction": 40,
    "post": 3,
}

_VIDEO_SUFFIXES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska", ".webm": "video/webm"}

_PRIVACY_BUILDERS = {
    "everyone": lambda: [InputPrivacyValueAllowAll()],
    "contacts": lambda: [InputPrivacyValueAllowContacts()],
}


class StoriesAlreadyRunningError(RuntimeError):
    """Raised when another stories job already owns the account pool."""


@dataclass
class StoryResultRow:
    account_phone: str
    state: str = "pending"
    message: str = ""


@dataclass(frozen=True)
class StoriesOptions:
    action_type: str
    target_chat: str
    target_story_id: int
    reaction_emoji: str
    media_path: str
    caption: str
    privacy: str
    period_hours: Optional[int]
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
    results: List[StoryResultRow] = field(default_factory=list)
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


class StoriesManager:
    """Owns one cancellable story view/reaction/post job."""

    def __init__(
        self,
        accounts: List[AccountConfig],
        pool_guard: PoolAccessGuard,
        session_encryption_key: Optional[bytes] = None,
        redis_client: Optional[Any] = None,
        proxy_repository: Optional[Any] = None,
        registry: Optional[AccountRegistry] = None,
        warmup_policy: Optional[WarmupPolicy] = None,
    ) -> None:
        self._accounts_by_phone = {self._phone_key(a.phone): a for a in accounts}
        self._pool_guard = pool_guard
        self._session_encryption_key = session_encryption_key
        self._redis_client = redis_client
        self._proxy_repository = proxy_repository
        self._registry = registry
        self._warmup_policy = warmup_policy
        self._run: Optional[_Run] = None

    @staticmethod
    def _phone_key(phone: str) -> str:
        return re.sub(r"[^0-9]", "", phone or "")

    def _delay_multiplier(self, phone: str) -> float:
        if self._warmup_policy is None:
            return 1.0
        return self._warmup_policy.delay_multiplier(account_age_days(self._registry, phone))

    def _capped_daily_limit(self, phone: str, base_cap: int) -> int:
        if self._warmup_policy is None:
            return base_cap
        warmup_cap = self._warmup_policy.daily_message_cap(account_age_days(self._registry, phone))
        return min(base_cap, warmup_cap) if base_cap > 0 else warmup_cap

    def register_account(self, account: AccountConfig) -> None:
        self._accounts_by_phone[self._phone_key(account.phone)] = account

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def start(
        self,
        *,
        action_type: str,
        target_chat: str = "",
        target_story_id: int = 0,
        reaction_emoji: str = "",
        media_path: str = "",
        caption: str = "",
        privacy: str = "everyone",
        period_hours: Optional[int] = None,
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
        require_proxy: bool = True,
        results_dir: str = "exports",
    ) -> str:
        if self.is_running:
            raise StoriesAlreadyRunningError("A stories job is already running.")
        if action_type not in ACTION_TYPES:
            raise ValueError(f"Unknown action_type: {action_type!r}")
        if action_type in ("view", "reaction"):
            if not target_chat.strip():
                raise ValueError("target_chat is required.")
            if target_story_id <= 0:
                raise ValueError("target_story_id must be a positive story ID.")
        if action_type == "reaction" and not reaction_emoji.strip():
            raise ValueError("reaction_emoji is required for the reaction action.")
        if action_type == "post":
            if not media_path.strip():
                raise ValueError("media_path is required for the post action.")
            if not Path(media_path).expanduser().is_file():
                raise ValueError(f"Story media file not found: {media_path}")
            if privacy not in _PRIVACY_BUILDERS:
                raise ValueError(f"Unknown privacy: {privacy!r}")

        senders = self._normalize_senders(sender_phones)
        if not senders:
            raise ValueError("No valid sender accounts available.")
        if max_total_accounts is not None and max_total_accounts > 0:
            senders = senders[: int(max_total_accounts)]

        sender_accounts = [self._accounts_by_phone[self._phone_key(p)] for p in senders]
        if require_proxy:
            ensure_all_proxied(sender_accounts)
            ensure_no_shared_proxies(sender_accounts)
        unproxied = unproxied_phones(sender_accounts)

        delay_min = max(0.0, float(delay_min_sec))
        delay_max = max(delay_min, float(delay_max_sec))
        stream_count = max(1, min(int(streams), len(senders)))
        cap = int(daily_cap_per_account) if daily_cap_per_account else DEFAULT_DAILY_CAPS[action_type]

        try:
            self._pool_guard.try_acquire("stories")
        except PoolBusyError as exc:
            raise StoriesAlreadyRunningError(str(exc)) from exc

        options = StoriesOptions(
            action_type=action_type,
            target_chat=target_chat.strip(),
            target_story_id=int(target_story_id),
            reaction_emoji=reaction_emoji.strip(),
            media_path=media_path.strip(),
            caption=caption,
            privacy=privacy,
            period_hours=period_hours,
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
            results=[StoryResultRow(account_phone=phone) for phone in senders],
            unproxied_senders=unproxied,
        )

        async def _runner() -> None:
            try:
                await self._run_all(run, senders, options)
            except Exception as exc:
                logger.exception("Stories job %s failed", job_id)
                run.error = str(exc)
            finally:
                try:
                    run.export_path = self._export_results(run, options.results_dir)
                except Exception as exc:
                    logger.exception("Could not export stories results")
                    run.error = run.error or f"Result export failed: {exc}"
                run.finished = True
                self._pool_guard.release("stories")

        run.task = asyncio.create_task(_runner(), name=f"api-stories-{job_id}")
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

    async def _run_all(self, run: _Run, senders: List[str], options: StoriesOptions) -> None:
        semaphore = asyncio.Semaphore(options.streams)

        async def worker(phone: str, row: StoryResultRow) -> None:
            async with semaphore:
                if run.shutdown_event.is_set():
                    row.state = "skipped"
                    row.message = "Stopped before start."
                    run.failed += 1
                    return
                try:
                    await asyncio.wait_for(
                        run.shutdown_event.wait(),
                        timeout=random.uniform(options.delay_min_sec, options.delay_max_sec)
                        * self._delay_multiplier(phone),
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
        self, run: _Run, phone: str, row: StoryResultRow, options: StoriesOptions
    ) -> None:
        cap = self._capped_daily_limit(phone, options.daily_cap_per_account)
        if self._redis_client is not None and cap > 0:
            allowed = await self._check_daily_cap(phone, options, cap)
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
            row.message = f"{type(exc).__name__}: {scrub_secrets(str(exc))}"
            run.failed += 1
            logger.warning("Stories action failed for %s: %s", phone, exc)
        finally:
            if client is not None:
                await self._disconnect(phone, client)

    async def _attempt_with_flood_wait(
        self, run: _Run, client, row: StoryResultRow, options: StoriesOptions
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

    async def _perform_action(self, client, options: StoriesOptions) -> None:
        if options.action_type == "view":
            peer = await client.get_input_entity(options.target_chat)
            await client(ReadStoriesRequest(peer=peer, max_id=options.target_story_id))
        elif options.action_type == "reaction":
            peer = await client.get_input_entity(options.target_chat)
            await client(
                SendStoryReactionRequest(
                    peer=peer,
                    story_id=options.target_story_id,
                    reaction=ReactionEmoji(emoticon=options.reaction_emoji),
                    add_to_recent=True,
                )
            )
        elif options.action_type == "post":
            media = await self._build_story_media(client, options.media_path)
            period = options.period_hours * 3600 if options.period_hours else 86400
            await client(
                SendStoryRequest(
                    peer="me",
                    media=media,
                    privacy_rules=_PRIVACY_BUILDERS[options.privacy](),
                    caption=options.caption or None,
                    period=period,
                    random_id=helpers.generate_random_long(),
                )
            )

    @staticmethod
    async def _build_story_media(client, media_path: str):
        path = Path(media_path).expanduser()
        file_handle = await client.upload_file(str(path))
        suffix = path.suffix.casefold()
        if suffix in _VIDEO_SUFFIXES:
            # Best-effort: Telegram transcodes uploaded story video server-side and
            # tolerates approximate duration/w/h, but a probed value (ffprobe/moviepy)
            # would be more correct if this ever needs to get stricter.
            return InputMediaUploadedDocument(
                file=file_handle,
                mime_type=_VIDEO_SUFFIXES[suffix],
                attributes=[DocumentAttributeVideo(duration=0, w=0, h=0, supports_streaming=True)],
            )
        return InputMediaUploadedPhoto(file=file_handle)

    async def _check_daily_cap(self, phone: str, options: StoriesOptions, cap: int) -> bool:
        from tg_pool.messaging.lua_storage import RedisRateLimiter

        limiter = RedisRateLimiter(
            self._redis_client,
            pool_id=f"stories:{options.action_type}:{self._phone_key(phone)}",
            capacity=cap,
            refill_rate=cap / 86400.0,
        )
        allowed, _reason = await limiter.check_and_consume(phone)
        return allowed

    def _auto_stop_reached(self, run: _Run, options: StoriesOptions) -> bool:
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

    async def _record_ban_signal(self, phone: str) -> None:
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

    async def _connect(self, phone: str):
        account = self._accounts_by_phone.get(self._phone_key(phone))
        if account is None:
            raise ValueError(f"Sender account not found: {phone}")
        if self._session_encryption_key is not None:
            from tg_pool.accounts.session_crypto import ensure_decrypted

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
                from tg_pool.accounts.session_crypto import ensure_encrypted

                ensure_encrypted(account.session_path, self._session_encryption_key)

    @staticmethod
    def _export_results(run: _Run, results_dir: str) -> str:
        output_dir = Path(results_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"stories-{run.action_type}-{run.job_id}.xlsx"
        pd.DataFrame(
            [
                {"Account": row.account_phone, "Status": row.state, "Details": row.message}
                for row in run.results
            ]
        ).to_excel(path, index=False)
        return str(path.resolve())
