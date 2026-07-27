"""Send Telegram messages to user IDs from an exported audience database."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

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
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import DeleteHistoryRequest
from telethon.tl.types import InputPeerUser, PeerUser, User

from src.accounts.connection_manager import ClientFactory
from src.api.pool_guard import PoolAccessGuard, PoolBusyError
from src.config import AccountConfig
from src.extraction.entity_resolver import UniversalEntityResolver
from src.messaging.forward_source import resolve_forward_source
from src.messaging.messaging_service import render_template
from src.messaging.spintax import resolve_spintax

logger = logging.getLogger(__name__)

_INT_RE = re.compile(r"-?\d+")


class SendByIdAlreadyRunningError(RuntimeError):
    """Raised when another ID messaging job owns the account pool."""


class _StopRequested(RuntimeError):
    """Internal control flow used to end an interruptible wait cleanly."""


@dataclass(frozen=True)
class IdRecipient:
    user_id: int
    access_hash: Optional[int] = None
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    donor: str = ""


@dataclass
class SendByIdResultRow:
    recipient_id: int
    sender_phone: str = ""
    username: str = ""
    donor: str = ""
    state: str = "pending"
    message: str = ""
    cycle: int = 1


@dataclass(frozen=True)
class SendByIdOptions:
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
    leave_donor_groups: bool
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
    recipients: List[IdRecipient]
    results: List[SendByIdResultRow] = field(default_factory=list)
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
    export_path: Optional[str] = None


def _normalized_header(value: Any) -> str:
    return re.sub(r"[^a-zа-я0-9]", "", str(value).strip().casefold())


def _first_present(mapping: Dict[str, Any], aliases: Iterable[str]) -> Any:
    for alias in aliases:
        if alias in mapping:
            value = mapping[alias]
            if value is not None and not pd.isna(value) and str(value).strip():
                return value
    return None


def _as_optional_int(value: Any) -> Optional[int]:
    if value is None or pd.isna(value):
        return None
    match = _INT_RE.search(str(value).strip())
    if not match:
        return None
    return int(match.group())


def _recipient_from_mapping(raw: Dict[str, Any]) -> Optional[IdRecipient]:
    mapping = {_normalized_header(key): value for key, value in raw.items()}
    user_id = _as_optional_int(
        _first_present(mapping, ("id", "userid", "telegramid", "peerid"))
    )
    if user_id is None or user_id <= 0:
        return None

    access_hash = _as_optional_int(
        _first_present(mapping, ("accesshash", "hash", "useraccesshash"))
    )
    username = str(
        _first_present(mapping, ("username", "user", "юзернейм", "логин")) or ""
    ).strip().lstrip("@")
    first_name = str(
        _first_present(mapping, ("firstname", "name", "имя")) or ""
    ).strip()
    last_name = str(
        _first_present(mapping, ("lastname", "surname", "фамилия")) or ""
    ).strip()
    donor = str(
        _first_present(
            mapping,
            (
                "donor",
                "source",
                "sourcechat",
                "group",
                "chat",
                "источник",
                "донор",
            ),
        )
        or ""
    ).strip()

    if not donor and raw:
        candidate = str(list(raw.values())[-1] or "").strip()
        if candidate.startswith(("@", "http://", "https://", "t.me/", "-100")):
            donor = candidate

    return IdRecipient(
        user_id=user_id,
        access_hash=access_hash,
        username=username,
        first_name=first_name,
        last_name=last_name,
        donor=donor,
    )


def _read_tabular(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.casefold()
    if suffix in {".xlsx", ".xls"}:
        sheets = pd.read_excel(path, sheet_name=None, dtype=object)
        return [
            row
            for frame in sheets.values()
            for row in frame.to_dict(orient="records")
        ]
    if suffix == ".csv":
        return pd.read_csv(path, dtype=object).to_dict(orient="records")
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, dict):
            for key in ("users", "recipients", "results", "data"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
            else:
                payload = [payload]
        if not isinstance(payload, list):
            raise ValueError("JSON database must contain an array of recipients.")
        return [item for item in payload if isinstance(item, dict)]

    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in re.split(r"[,;\t]", line)]
        if len(parts) == 1:
            rows.append({"id": parts[0]})
        else:
            rows.append(
                {
                    "id": parts[0],
                    "access_hash": parts[1] if len(parts) > 1 else "",
                    "username": parts[2] if len(parts) > 2 else "",
                    "source": parts[3] if len(parts) > 3 else "",
                }
            )
    return rows


def load_id_database(database_path: str) -> List[IdRecipient]:
    """Load and deduplicate a supported local audience database by Telegram ID."""
    path = Path(database_path).expanduser()
    if not path.is_file():
        raise ValueError(f"Audience database not found: {path}")
    if path.suffix.casefold() not in {".txt", ".csv", ".json", ".xlsx", ".xls"}:
        raise ValueError("Supported audience databases: .txt, .csv, .json, .xlsx, .xls.")

    recipients: List[IdRecipient] = []
    seen: set[int] = set()
    for raw in _read_tabular(path):
        recipient = _recipient_from_mapping(raw)
        if recipient is not None and recipient.user_id not in seen:
            seen.add(recipient.user_id)
            recipients.append(recipient)
    if not recipients:
        raise ValueError("The audience database contains no valid Telegram user IDs.")
    return recipients


class SendByIdManager:
    """Owns one cancellable, optionally repeating Telegram ID messaging job."""

    def __init__(
        self,
        accounts: List[AccountConfig],
        pool_guard: PoolAccessGuard,
        session_encryption_key: Optional[bytes] = None,
    ) -> None:
        self._accounts_by_phone = {self._phone_key(a.phone): a for a in accounts}
        self._pool_guard = pool_guard
        self._session_encryption_key = session_encryption_key
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
        database_path: str,
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
        leave_donor_groups: bool = False,
        pin_message: bool = False,
        video_note: bool = False,
        self_destruct_sec: Optional[int] = None,
        schedule_at: Optional[datetime] = None,
        streams: int = 1,
        auto_stop_ban: int = 0,
        auto_stop_spamblock: int = 0,
        auto_stop_floodwait: int = 0,
        repeat_every_hours: Optional[float] = None,
        results_dir: str = "exports",
    ) -> str:
        if self.is_running:
            raise SendByIdAlreadyRunningError("A send-by-ID job is already running.")

        recipients = load_id_database(database_path)
        senders = self._normalize_senders(sender_phones)
        if not senders:
            raise ValueError("No valid sender accounts available.")

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
            self._pool_guard.try_acquire("send_by_id")
        except PoolBusyError as exc:
            raise SendByIdAlreadyRunningError(str(exc)) from exc

        options = SendByIdOptions(
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
            leave_donor_groups=leave_donor_groups,
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
        )

        async def _runner() -> None:
            try:
                await self._run_cycles(run, senders, options)
            except Exception as exc:
                logger.exception("Send-by-ID job %s failed", job_id)
                run.error = str(exc)
            finally:
                try:
                    run.export_path = self._export_results(run, options.results_dir)
                except Exception as exc:
                    logger.exception("Could not export send-by-ID results")
                    run.error = run.error or f"Result export failed: {exc}"
                run.finished = True
                self._pool_guard.release("send_by_id")

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
            "export_path": run.export_path,
            "results": [
                {
                    "recipient_id": row.recipient_id,
                    "sender_phone": row.sender_phone,
                    "username": row.username,
                    "donor": row.donor,
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
        options: SendByIdOptions,
    ) -> None:
        while not run.shutdown_event.is_set():
            assignments = self._assign_recipients(
                run.recipients,
                senders,
                options.sms_per_account_min,
                options.sms_per_account_max,
            )
            cycle_rows = [
                SendByIdResultRow(
                    recipient_id=recipient.user_id,
                    sender_phone=sender or "",
                    username=recipient.username,
                    donor=recipient.donor,
                    state="pending" if sender else "skipped",
                    message="Queued" if sender else "All selected accounts reached their quota.",
                    cycle=run.cycle,
                )
                for recipient, sender in assignments
            ]
            run.results.extend(cycle_rows)
            run.failed += sum(row.state == "skipped" for row in cycle_rows)

            per_sender: Dict[str, List[tuple[IdRecipient, SendByIdResultRow]]] = {}
            for (recipient, sender), row in zip(assignments, cycle_rows):
                if sender:
                    per_sender.setdefault(sender, []).append((recipient, row))

            semaphore = asyncio.Semaphore(options.streams)

            async def worker(phone: str, items: List[tuple[IdRecipient, SendByIdResultRow]]) -> None:
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
        recipients: List[IdRecipient],
        senders: List[str],
        minimum: int,
        maximum: int,
    ) -> List[tuple[IdRecipient, Optional[str]]]:
        quotas = {sender: random.randint(minimum, maximum) for sender in senders}
        counts = {sender: 0 for sender in senders}
        sender_index = 0
        assignments: List[tuple[IdRecipient, Optional[str]]] = []
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
        items: List[tuple[IdRecipient, SendByIdResultRow]],
        options: SendByIdOptions,
    ) -> None:
        client = None
        donor_cache: Dict[str, Dict[int, User]] = {}
        donor_entities: Dict[str, Any] = {}
        try:
            client = await self._connect(phone)
            for recipient, row in items:
                if run.shutdown_event.is_set() or self._auto_stop_reached(run, options):
                    row.state = "skipped"
                    row.message = "Stopped before send."
                    run.failed += 1
                    continue
                await self._deliver(run, client, phone, recipient, row, options, donor_cache, donor_entities)
                if not run.shutdown_event.is_set():
                    try:
                        await asyncio.wait_for(
                            run.shutdown_event.wait(),
                            timeout=random.uniform(options.delay_min_sec, options.delay_max_sec),
                        )
                    except asyncio.TimeoutError:
                        pass
        except (UserDeactivatedBanError, AuthKeyUnregisteredError) as exc:
            run.ban_count += 1
            self._fail_pending(items, f"Sender banned or unauthorized: {type(exc).__name__}", run)
        except PeerFloodError as exc:
            run.spamblock_count += 1
            self._fail_pending(items, f"Sender spam-blocked: {type(exc).__name__}", run)
        except Exception as exc:
            self._fail_pending(items, f"Sender unavailable: {type(exc).__name__}: {exc}", run)
        finally:
            if client is not None and options.leave_donor_groups:
                await self._leave_donors(client, donor_entities.values())
            if client is not None:
                await self._disconnect(phone, client)

    async def _deliver(
        self,
        run: _Run,
        client,
        phone: str,
        recipient: IdRecipient,
        row: SendByIdResultRow,
        options: SendByIdOptions,
        donor_cache: Dict[str, Dict[int, User]],
        donor_entities: Dict[str, Any],
    ) -> None:
        row.state = "resolving"
        row.message = f"Resolving user {recipient.user_id}"
        try:
            peer = await self._resolve_recipient(
                client,
                recipient,
                donor_cache,
                donor_entities,
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
                        logger.debug("Could not pin message for %s: %s", recipient.user_id, exc)
            if options.delete_dialog:
                try:
                    await client(DeleteHistoryRequest(peer=peer, max_id=0, revoke=False))
                except Exception as exc:
                    logger.debug("Could not delete dialog for %s: %s", recipient.user_id, exc)

            row.state = "scheduled" if options.schedule_at is not None else "sent"
            row.message = (
                f"Scheduled for {options.schedule_at.isoformat(sep=' ', timespec='minutes')}"
                if options.schedule_at is not None
                else f"Delivered to user {recipient.user_id}"
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
            row.message = f"{type(exc).__name__}: {exc}"
            run.failed += 1
            logger.warning("Send-by-ID failed %s -> %s: %s", phone, recipient.user_id, exc)

    async def _send_with_flood_wait(
        self,
        run: _Run,
        client,
        peer,
        recipient: IdRecipient,
        options: SendByIdOptions,
        row: SendByIdResultRow,
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
        recipient: IdRecipient,
        options: SendByIdOptions,
    ) -> List[Any]:
        variables = {
            "username": recipient.username or "",
            "first_name": recipient.first_name,
            "last_name": recipient.last_name,
            "id": str(recipient.user_id),
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
        recipient: IdRecipient,
        donor_cache: Dict[str, Dict[int, User]],
        donor_entities: Dict[str, Any],
    ):
        if recipient.access_hash is not None:
            return InputPeerUser(recipient.user_id, recipient.access_hash)
        if recipient.username:
            try:
                return await client.get_input_entity(recipient.username)
            except Exception:
                pass
        try:
            entity = await client.get_entity(recipient.user_id)
            if isinstance(entity, User):
                return entity
        except Exception:
            pass
        if not recipient.donor:
            raise ValueError(
                "ID is unknown to this session; add access_hash, username, or donor/source chat."
            )

        donor_key = recipient.donor.casefold()
        if donor_key not in donor_cache:
            entity = await self._join_or_resolve_donor(client, recipient.donor)
            donor_entities[donor_key] = entity
            members: Dict[int, User] = {}
            async for user in client.iter_participants(entity, aggressive=False):
                if isinstance(user, User):
                    members[int(user.id)] = user
            donor_cache[donor_key] = members
        user = donor_cache[donor_key].get(recipient.user_id)
        if user is None:
            raise ValueError(f"User {recipient.user_id} was not found in donor {recipient.donor}.")
        return user

    @staticmethod
    async def _join_or_resolve_donor(client, donor: str):
        resolved = await UniversalEntityResolver(client).resolve(donor.strip())
        entity = resolved.entity
        try:
            await client(JoinChannelRequest(entity))
        except Exception:
            pass
        return entity

    @staticmethod
    async def _leave_donors(client, entities: Iterable[Any]) -> None:
        for entity in entities:
            try:
                await client(LeaveChannelRequest(entity))
            except Exception as exc:
                logger.debug("Could not leave donor %s: %s", entity, exc)

    def _auto_stop_reached(self, run: _Run, options: SendByIdOptions) -> bool:
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
        items: List[tuple[IdRecipient, SendByIdResultRow]],
        message: str,
        run: _Run,
    ) -> None:
        for _, row in items:
            if row.state in {"pending", "resolving", "waiting"}:
                row.state = "failed"
                row.message = message
                run.failed += 1

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
        path = output_dir / f"sending-sms-by-id-{run.job_id}.xlsx"
        pd.DataFrame(
            [
                {
                    "Cycle": row.cycle,
                    "ID": row.recipient_id,
                    "Username": row.username,
                    "Donor": row.donor,
                    "Sender": row.sender_phone,
                    "Status": row.state,
                    "Details": row.message,
                }
                for row in run.results
            ]
        ).to_excel(path, index=False)
        return str(path.resolve())
