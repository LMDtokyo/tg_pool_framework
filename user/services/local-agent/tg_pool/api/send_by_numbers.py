"""Send Telegram messages to recipients resolved by phone number."""

from __future__ import annotations

import asyncio
import logging
import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    PeerFloodError,
    PeerIdInvalidError,
    UserDeactivatedBanError,
    UserIsBlockedError,
    UserPrivacyRestrictedError,
)
from telethon.tl.functions.contacts import DeleteContactsRequest, ImportContactsRequest
from telethon.tl.functions.messages import DeleteHistoryRequest
from telethon.tl.types import InputPhoneContact, User

from tg_pool.accounts.account_registry import AccountRegistry
from tg_pool.accounts.connection_manager import ClientFactory
from tg_pool.accounts.proxy_safety import ensure_all_proxied, ensure_no_shared_proxies, unproxied_phones
from tg_pool.accounts.warmup_policy import WarmupPolicy, account_age_days
from tg_pool.api.pool_guard import PoolAccessGuard, PoolBusyError
from tg_pool.api.security_utils import scrub_secrets
from tg_pool.config import AccountConfig
from tg_pool.messaging.forward_source import resolve_forward_source
from tg_pool.messaging.messaging_service import render_template
from tg_pool.messaging.spintax import resolve_spintax

logger = logging.getLogger(__name__)

class SendByNumbersAlreadyRunningError(RuntimeError):
    """Raised when another phone-number messaging job owns the account pool."""


class _StopRequested(RuntimeError):
    """Internal control flow used to end an interruptible wait cleanly."""


@dataclass(frozen=True)
class PhoneRecipient:
    phone: str


@dataclass
class SendByNumbersResultRow:
    recipient_phone: str
    sender_phone: str = ""
    state: str = "pending"
    message: str = ""
    cycle: int = 1


@dataclass(frozen=True)
class SendByNumbersOptions:
    message: str
    media_paths: List[str]
    forward_links: List[str]
    bot_relay_username: Optional[str]
    bot_relay_message_ids: List[int]
    sms_per_account_min: int
    sms_per_account_max: int
    delay_min_sec: float
    delay_max_sec: float
    max_flood_wait_sec: float
    delete_dialog: bool
    link_preview: bool
    silent: bool
    auto_repost: bool
    remove_imported_contacts: bool
    pin_message: bool
    video_note: bool
    self_destruct_sec: Optional[int]
    schedule_at: Optional[datetime]
    streams: int
    auto_stop_ban: int
    auto_stop_spamblock: int
    auto_stop_floodwait: int
    repeat_every_hours: Optional[float]
    results_dir: str


@dataclass
class _Run:
    job_id: str
    shutdown_event: asyncio.Event
    recipients: List[PhoneRecipient]
    results: List[SendByNumbersResultRow] = field(default_factory=list)
    task: Optional[asyncio.Task] = None
    sent: int = 0
    failed: int = 0
    finished: bool = False
    error: Optional[str] = None
    per_account: Dict[str, int] = field(default_factory=dict)
    ban_count: int = 0
    spamblock_count: int = 0
    floodwait_count: int = 0
    cycle: int = 1
    unproxied_senders: List[str] = field(default_factory=list)
    export_path: Optional[str] = None


def normalize_phone(value: str) -> Optional[str]:
    digits = re.sub(r"[^0-9]", "", value or "")
    if len(digits) < 7 or len(digits) > 16:
        return None
    return f"+{digits}"


class SendByNumbersManager:
    """Owns one cancellable, optionally repeating Telegram ID messaging job."""

    def __init__(
        self,
        accounts: List[AccountConfig],
        pool_guard: PoolAccessGuard,
        session_encryption_key: Optional[bytes] = None,
        proxy_repository: Optional[Any] = None,
        redis_client: Optional[Any] = None,
        registry: Optional[AccountRegistry] = None,
        warmup_policy: Optional[WarmupPolicy] = None,
    ) -> None:
        self._accounts_by_phone = {self._phone_key(a.phone): a for a in accounts}
        self._pool_guard = pool_guard
        self._session_encryption_key = session_encryption_key
        self._proxy_repository = proxy_repository
        self._redis_client = redis_client
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

    async def _daily_cap_allows(self, phone: str) -> bool:
        if self._warmup_policy is None or self._redis_client is None:
            return True
        cap = self._warmup_policy.daily_message_cap(account_age_days(self._registry, phone))
        from tg_pool.messaging.lua_storage import RedisRateLimiter

        limiter = RedisRateLimiter(
            self._redis_client,
            pool_id=f"send_by_numbers:{self._phone_key(phone)}",
            capacity=cap,
            refill_rate=cap / 86400.0,
        )
        allowed, _reason = await limiter.check_and_consume(phone)
        return allowed

    def register_account(self, account: AccountConfig) -> None:
        self._accounts_by_phone[self._phone_key(account.phone)] = account

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def start(
        self,
        *,
        phone_numbers: List[str],
        message: str = "",
        sender_phones: Optional[List[str]] = None,
        media_paths: Optional[List[str]] = None,
        forward_links: Optional[List[str]] = None,
        bot_relay_username: Optional[str] = None,
        bot_relay_message_ids: Optional[List[int]] = None,
        sms_per_account_min: int = 1,
        sms_per_account_max: int = 40,
        delay_min_sec: float = 1.0,
        delay_max_sec: float = 10.0,
        max_flood_wait_sec: float = 500.0,
        delete_dialog: bool = False,
        link_preview: bool = True,
        silent: bool = False,
        auto_repost: bool = False,
        remove_imported_contacts: bool = True,
        pin_message: bool = False,
        video_note: bool = False,
        self_destruct_sec: Optional[int] = None,
        schedule_at: Optional[datetime] = None,
        streams: int = 1,
        auto_stop_ban: int = 0,
        auto_stop_spamblock: int = 0,
        auto_stop_floodwait: int = 0,
        repeat_every_hours: Optional[float] = None,
        require_proxy: bool = True,
        results_dir: str = "exports",
    ) -> str:
        if self.is_running:
            raise SendByNumbersAlreadyRunningError("A send-by-numbers job is already running.")

        recipients: List[PhoneRecipient] = []
        seen_recipients: set[str] = set()
        for raw in phone_numbers:
            normalized = normalize_phone(raw)
            if normalized and normalized not in seen_recipients:
                recipients.append(PhoneRecipient(phone=normalized))
                seen_recipients.add(normalized)
        if not recipients:
            raise ValueError("No valid phone numbers provided.")
        senders = self._normalize_senders(sender_phones)
        if not senders:
            raise ValueError("No valid sender accounts available.")

        sender_accounts = [self._accounts_by_phone[self._phone_key(p)] for p in senders]
        if require_proxy:
            ensure_all_proxied(sender_accounts)
            ensure_no_shared_proxies(sender_accounts)
        unproxied = unproxied_phones(sender_accounts)

        clean_media = [str(item).strip() for item in media_paths or [] if str(item).strip()]
        clean_links = [str(item).strip() for item in forward_links or [] if str(item).strip()]
        clean_bot_ids = [int(item) for item in bot_relay_message_ids or [] if int(item) > 0]
        if not message.strip() and not clean_media and not clean_links and not clean_bot_ids:
            raise ValueError("Message text, media, a post link, or a Postbot post is required.")

        minimum = max(1, int(sms_per_account_min))
        maximum = max(minimum, int(sms_per_account_max))
        delay_min = max(0.0, float(delay_min_sec))
        delay_max = max(delay_min, float(delay_max_sec))
        max_wait = max(0.0, float(max_flood_wait_sec))
        stream_count = max(1, min(int(streams), len(senders)))
        repeat_hours = (
            max(float(repeat_every_hours), 1 / 60)
            if repeat_every_hours is not None
            else None
        )
        if schedule_at is not None and schedule_at <= datetime.now(schedule_at.tzinfo):
            raise ValueError("Scheduled sending time must be in the future.")

        try:
            self._pool_guard.try_acquire("send_by_numbers")
        except PoolBusyError as exc:
            raise SendByNumbersAlreadyRunningError(str(exc)) from exc

        options = SendByNumbersOptions(
            message=message,
            media_paths=clean_media,
            forward_links=clean_links,
            bot_relay_username=(bot_relay_username or "").strip() or None,
            bot_relay_message_ids=clean_bot_ids,
            sms_per_account_min=minimum,
            sms_per_account_max=maximum,
            delay_min_sec=delay_min,
            delay_max_sec=delay_max,
            max_flood_wait_sec=max_wait,
            delete_dialog=delete_dialog,
            link_preview=link_preview,
            silent=silent,
            auto_repost=auto_repost,
            remove_imported_contacts=remove_imported_contacts,
            pin_message=pin_message,
            video_note=video_note,
            self_destruct_sec=self_destruct_sec,
            schedule_at=schedule_at,
            streams=stream_count,
            auto_stop_ban=max(0, int(auto_stop_ban)),
            auto_stop_spamblock=max(0, int(auto_stop_spamblock)),
            auto_stop_floodwait=max(0, int(auto_stop_floodwait)),
            repeat_every_hours=repeat_hours,
            results_dir=results_dir or "exports",
        )
        job_id = uuid.uuid4().hex[:12]
        run = _Run(
            job_id=job_id,
            shutdown_event=asyncio.Event(),
            recipients=recipients,
            unproxied_senders=unproxied,
        )

        async def _runner() -> None:
            try:
                await self._run_cycles(run, senders, options)
            except Exception as exc:
                logger.exception("Send-by-numbers job %s failed", job_id)
                run.error = str(exc)
            finally:
                try:
                    run.export_path = self._export_results(run, options.results_dir)
                except Exception as exc:
                    logger.exception("Could not export send-by-numbers results")
                    run.error = run.error or f"Result export failed: {exc}"
                run.finished = True
                self._pool_guard.release("send_by_numbers")

        run.task = asyncio.create_task(_runner(), name=f"api-send-by-id-{job_id}")
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
            "total": len(run.results),
            "sent": run.sent,
            "failed": run.failed,
            "per_account": dict(run.per_account),
            "finished": run.finished,
            "error": run.error,
            "ban_count": run.ban_count,
            "spamblock_count": run.spamblock_count,
            "floodwait_count": run.floodwait_count,
            "cycle": run.cycle,
            "unproxied_senders": run.unproxied_senders,
            "export_path": run.export_path,
            "results": [
                {
                    "recipient_phone": row.recipient_phone,
                    "sender_phone": row.sender_phone,
                    "state": row.state,
                    "message": row.message,
                    "cycle": row.cycle,
                }
                for row in run.results
            ],
        }

    async def _run_cycles(
        self,
        run: _Run,
        senders: List[str],
        options: SendByNumbersOptions,
    ) -> None:
        while not run.shutdown_event.is_set():
            assignments = self._assign_recipients(
                run.recipients,
                senders,
                options.sms_per_account_min,
                options.sms_per_account_max,
            )
            cycle_rows = [
                SendByNumbersResultRow(
                    recipient_phone=recipient.phone,
                    sender_phone=sender or "",
                    state="pending" if sender else "skipped",
                    message="Queued" if sender else "All selected accounts reached their quota.",
                    cycle=run.cycle,
                )
                for recipient, sender in assignments
            ]
            run.results.extend(cycle_rows)
            run.failed += sum(row.state == "skipped" for row in cycle_rows)

            per_sender: Dict[str, List[tuple[PhoneRecipient, SendByNumbersResultRow]]] = {}
            for (recipient, sender), row in zip(assignments, cycle_rows):
                if sender:
                    per_sender.setdefault(sender, []).append((recipient, row))

            semaphore = asyncio.Semaphore(options.streams)

            async def worker(phone: str, items: List[tuple[PhoneRecipient, SendByNumbersResultRow]]) -> None:
                async with semaphore:
                    await self._run_sender(run, phone, items, options)

            await asyncio.gather(
                *(worker(phone, items) for phone, items in per_sender.items())
            )
            if run.shutdown_event.is_set() or options.repeat_every_hours is None:
                break
            run.cycle += 1
            try:
                await asyncio.wait_for(
                    run.shutdown_event.wait(),
                    timeout=options.repeat_every_hours * 3600,
                )
            except asyncio.TimeoutError:
                pass

    @staticmethod
    def _assign_recipients(
        recipients: List[PhoneRecipient],
        senders: List[str],
        minimum: int,
        maximum: int,
    ) -> List[tuple[PhoneRecipient, Optional[str]]]:
        quotas = {sender: random.randint(minimum, maximum) for sender in senders}
        counts = {sender: 0 for sender in senders}
        sender_index = 0
        assignments: List[tuple[PhoneRecipient, Optional[str]]] = []
        for recipient in recipients:
            sender: Optional[str] = None
            for _ in range(len(senders)):
                candidate = senders[sender_index % len(senders)]
                sender_index += 1
                if counts[candidate] < quotas[candidate]:
                    counts[candidate] += 1
                    sender = candidate
                    break
            assignments.append((recipient, sender))
        return assignments

    async def _run_sender(
        self,
        run: _Run,
        phone: str,
        items: List[tuple[PhoneRecipient, SendByNumbersResultRow]],
        options: SendByNumbersOptions,
    ) -> None:
        client = None
        try:
            client = await self._connect(phone)
            for recipient, row in items:
                if run.shutdown_event.is_set() or self._auto_stop_reached(run, options):
                    row.state = "skipped"
                    row.message = "Stopped before send."
                    run.failed += 1
                    continue
                if not await self._daily_cap_allows(phone):
                    row.state = "skipped"
                    row.message = "Daily cap for this account reached."
                    run.failed += 1
                    continue
                await self._deliver(run, client, phone, recipient, row, options)
                if not run.shutdown_event.is_set():
                    try:
                        await asyncio.wait_for(
                            run.shutdown_event.wait(),
                            timeout=random.uniform(options.delay_min_sec, options.delay_max_sec)
                            * self._delay_multiplier(phone),
                        )
                    except asyncio.TimeoutError:
                        pass
        except (UserDeactivatedBanError, AuthKeyUnregisteredError) as exc:
            run.ban_count += 1
            self._fail_pending(items, f"Sender banned or unauthorized: {type(exc).__name__}", run)
            await self._record_ban_signal(phone)
        except PeerFloodError as exc:
            run.spamblock_count += 1
            self._fail_pending(items, f"Sender spam-blocked: {type(exc).__name__}", run)
            await self._record_ban_signal(phone)
        except Exception as exc:
            self._fail_pending(items, f"Sender unavailable: {type(exc).__name__}: {scrub_secrets(str(exc))}", run)
        finally:
            if client is not None:
                await self._disconnect(phone, client)

    async def _deliver(
        self,
        run: _Run,
        client,
        phone: str,
        recipient: PhoneRecipient,
        row: SendByNumbersResultRow,
        options: SendByNumbersOptions,
    ) -> None:
        row.state = "resolving"
        row.message = f"Resolving {recipient.phone}"
        try:
            peer = await self._resolve_recipient(
                client,
                recipient,
                remove_imported_contact=options.remove_imported_contacts,
            )
            sent_messages = await self._send_with_flood_wait(
                run,
                client,
                peer,
                recipient,
                options,
                row,
            )
            if options.pin_message and sent_messages:
                for sent in sent_messages:
                    try:
                        await client.pin_message(peer, sent, notify=False)
                    except Exception as exc:
                        logger.debug("Could not pin message for %s: %s", recipient.phone, exc)
            if options.delete_dialog:
                try:
                    await client(DeleteHistoryRequest(peer=peer, max_id=0, revoke=False))
                except Exception as exc:
                    logger.debug("Could not delete dialog for %s: %s", recipient.phone, exc)

            row.state = "scheduled" if options.schedule_at is not None else "sent"
            row.message = (
                f"Scheduled for {options.schedule_at.isoformat(sep=' ', timespec='minutes')}"
                if options.schedule_at is not None
                else f"Delivered to {recipient.phone}"
            )
            run.sent += 1
            run.per_account[phone] = run.per_account.get(phone, 0) + 1
        except FloodWaitError as exc:
            row.state = "failed"
            row.message = f"FloodWait {exc.seconds}s exceeds maximum timeout."
            run.failed += 1
        except _StopRequested:
            row.state = "skipped"
            row.message = "Stopped during wait."
            run.failed += 1
        except PeerFloodError:
            row.state = "failed"
            row.message = "Sender is restricted from contacting new users."
            run.failed += 1
            raise
        except (UserDeactivatedBanError, AuthKeyUnregisteredError):
            row.state = "failed"
            row.message = "Sender account is banned or unauthorized."
            run.failed += 1
            raise
        except (UserPrivacyRestrictedError, UserIsBlockedError, PeerIdInvalidError) as exc:
            row.state = "failed"
            row.message = type(exc).__name__
            run.failed += 1
        except Exception as exc:
            row.state = "failed"
            row.message = f"{type(exc).__name__}: {scrub_secrets(str(exc))}"
            run.failed += 1
            logger.warning("Send-by-numbers failed %s -> %s: %s", phone, recipient.phone, exc)

    async def _send_with_flood_wait(
        self,
        run: _Run,
        client,
        peer,
        recipient: PhoneRecipient,
        options: SendByNumbersOptions,
        row: SendByNumbersResultRow,
    ) -> List[Any]:
        while True:
            try:
                return await self._send_payload(client, peer, recipient, options)
            except FloodWaitError as exc:
                run.floodwait_count += 1
                if self._auto_stop_reached(run, options):
                    raise
                if exc.seconds > options.max_flood_wait_sec:
                    raise
                row.state = "waiting"
                row.message = f"FloodWait {exc.seconds}s; resuming automatically."
                try:
                    await asyncio.wait_for(
                        run.shutdown_event.wait(),
                        timeout=float(exc.seconds),
                    )
                    raise _StopRequested
                except asyncio.TimeoutError:
                    pass

    async def _send_payload(
        self,
        client,
        peer,
        recipient: PhoneRecipient,
        options: SendByNumbersOptions,
    ) -> List[Any]:
        variables = {
            "phone": recipient.phone,
            "username": getattr(peer, "username", "") or "",
            "first_name": getattr(peer, "first_name", "") or "",
            "last_name": getattr(peer, "last_name", "") or "",
            "id": str(getattr(peer, "id", "")),
        }
        text = render_template(resolve_spintax(options.message), variables)
        forward_link = random.choice(options.forward_links) if options.forward_links else None
        forward_source = resolve_forward_source(
            forward_link,
            options.bot_relay_username,
            options.bot_relay_message_ids,
        )
        media_path = random.choice(options.media_paths) if options.media_paths else None

        destination = "me" if options.auto_repost else peer
        first_hop_schedule = None if options.auto_repost else options.schedule_at
        sent: List[Any] = []
        if forward_source is not None:
            source_peer, message_id = forward_source
            forwarded = await client.forward_messages(
                destination,
                message_id,
                from_peer=source_peer,
                silent=options.silent,
                schedule=first_hop_schedule,
            )
            sent.extend(forwarded if isinstance(forwarded, list) else [forwarded])
            if text.strip():
                followup = await client.send_message(
                    destination,
                    text,
                    parse_mode="html",
                    silent=options.silent,
                    link_preview=options.link_preview,
                    schedule=first_hop_schedule,
                )
                sent.extend(followup if isinstance(followup, list) else [followup])
        elif media_path:
            kwargs: Dict[str, Any] = {
                "caption": text,
                "parse_mode": "html",
                "silent": options.silent,
                "schedule": first_hop_schedule,
            }
            if options.video_note:
                kwargs["video_note"] = True
            elif str(media_path).casefold().endswith(".ogg"):
                kwargs["voice_note"] = True
            if options.self_destruct_sec:
                kwargs["ttl"] = options.self_destruct_sec
            media = await client.send_file(destination, media_path, **kwargs)
            sent.extend(media if isinstance(media, list) else [media])
        else:
            message = await client.send_message(
                destination,
                text,
                parse_mode="html",
                silent=options.silent,
                link_preview=options.link_preview,
                schedule=first_hop_schedule,
            )
            sent.extend(message if isinstance(message, list) else [message])

        if options.auto_repost:
            reposted: List[Any] = []
            for staged in sent:
                forwarded = await client.forward_messages(
                    peer,
                    staged,
                    from_peer="me",
                    silent=options.silent,
                    schedule=options.schedule_at,
                )
                reposted.extend(forwarded if isinstance(forwarded, list) else [forwarded])
            return reposted
        return sent

    async def _resolve_recipient(
        self,
        client,
        recipient: PhoneRecipient,
        *,
        remove_imported_contact: bool,
    ) -> User:
        me = await client.get_me()
        me_id = int(me.id)
        digits = re.sub(r"[^0-9]", "", recipient.phone)
        candidates = list(dict.fromkeys([recipient.phone, digits, f"+{digits}"]))
        errors: List[str] = []

        for candidate in candidates:
            try:
                return self._as_phone_user(await client.get_entity(candidate), me_id)
            except Exception as exc:
                errors.append(f"get_entity({candidate}): {exc}")

        for candidate in candidates:
            contact = InputPhoneContact(
                client_id=random.randrange(1, 2**31 - 1),
                phone=candidate,
                first_name=candidate,
                last_name="",
            )
            try:
                imported = await client(ImportContactsRequest([contact]))
                users = [
                    user
                    for user in (getattr(imported, "users", None) or [])
                    if isinstance(user, User)
                ]
                matched = self._select_imported_phone_user(
                    users,
                    expected_digits=digits,
                    me_id=me_id,
                )
                if matched is None:
                    errors.append(f"import({candidate}): no matching Telegram user")
                    continue
                if remove_imported_contact:
                    try:
                        await client(DeleteContactsRequest(id=[matched]))
                    except Exception as exc:
                        logger.debug("Could not remove temporary contact %s: %s", recipient.phone, exc)
                return matched
            except Exception as exc:
                errors.append(f"import({candidate}): {exc}")

        raise LookupError(
            f"Could not resolve Telegram user for {recipient.phone}. Telegram may not "
            "allow this sender account to discover the number. Details: "
            + "; ".join(errors[-4:])
        )

    @classmethod
    def _select_imported_phone_user(
        cls,
        users: List[User],
        *,
        expected_digits: str,
        me_id: int,
    ) -> Optional[User]:
        fallback: Optional[User] = None
        for entity in users:
            try:
                user = cls._as_phone_user(entity, me_id)
            except LookupError:
                continue
            user_digits = re.sub(r"[^0-9]", "", getattr(user, "phone", "") or "")
            if user_digits and user_digits == expected_digits:
                return user
            fallback = fallback or user
        return fallback

    @staticmethod
    def _as_phone_user(entity, me_id: int) -> User:
        if not isinstance(entity, User):
            raise LookupError(f"Resolved entity is {type(entity).__name__}, expected User")
        if int(entity.id) == me_id:
            raise LookupError("Resolved recipient is the sender account itself")
        if getattr(entity, "bot", False):
            raise LookupError("Resolved recipient is a bot")
        if getattr(entity, "deleted", False):
            raise LookupError("Resolved recipient is a deleted account")
        return entity

    def _auto_stop_reached(self, run: _Run, options: SendByNumbersOptions) -> bool:
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

    @staticmethod
    def _fail_pending(
        items: List[tuple[PhoneRecipient, SendByNumbersResultRow]],
        message: str,
        run: _Run,
    ) -> None:
        for _, row in items:
            if row.state in {"pending", "resolving", "waiting"}:
                row.state = "failed"
                row.message = message
                run.failed += 1

    async def _record_ban_signal(self, phone: str) -> None:
        """A proxy can pass connectivity checks while still being a burned exit
        IP Telegram is banning every account through -- flag it, if tracked."""
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
        path = output_dir / f"send-by-numbers-{run.job_id}.xlsx"
        pd.DataFrame(
            [
                {
                    "Cycle": row.cycle,
                    "Phone": row.recipient_phone,
                    "Sender": row.sender_phone,
                    "Status": row.state,
                    "Details": row.message,
                }
                for row in run.results
            ]
        ).to_excel(path, index=False)
        return str(path.resolve())
