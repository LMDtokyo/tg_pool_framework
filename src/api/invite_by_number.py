"""
src/api/invite_by_number.py — Send invite-link DMs via saved Telethon sessions.

Resolves recipients as real Telegram users (username → user id → phone contact),
verifies the outgoing peer, and only then marks the send as successful.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from telethon.errors import FloodWaitError, PeerFloodError, UserPrivacyRestrictedError
from telethon.tl.functions.contacts import DeleteContactsRequest, ImportContactsRequest
from telethon.tl.types import InputPhoneContact, PeerUser, User

from src.accounts.connection_manager import ClientFactory
from src.api.pool_guard import PoolAccessGuard, PoolBusyError
from src.config import AccountConfig

logger = logging.getLogger(__name__)

_INVITE_LINK_RE = re.compile(r"https://t\.me/[A-Za-z0-9_+\-/]+", re.IGNORECASE)


class InviteByNumberAlreadyRunningError(RuntimeError):
    """Raised when an invite-by-number job is already in flight."""


@dataclass
class InviteSenderLink:
    sender_phone: str
    invite_link: str


@dataclass
class InviteRecipient:
    recipient_id: str
    username: Optional[str] = None
    phone: Optional[str] = None


@dataclass
class InviteResultRow:
    recipient_id: str
    sender_phone: str
    invite_link: str
    username: Optional[str] = None
    phone: Optional[str] = None
    state: str = "pending"
    message: str = ""


@dataclass
class _Run:
    job_id: str
    shutdown_event: asyncio.Event
    results: List[InviteResultRow]
    task: Optional[asyncio.Task] = None
    sent: int = 0
    failed: int = 0
    finished: bool = False
    error: Optional[str] = None
    per_account: Dict[str, int] = field(default_factory=dict)


def normalize_phone(value: str) -> Optional[str]:
    digits = re.sub(r"[^0-9]", "", value or "")
    if len(digits) < 7 or len(digits) > 16:
        return None
    return f"+{digits}"


def normalize_recipient_id(value: str) -> Optional[str]:
    """Normalize a Telegram user id (digits only, never a +phone)."""
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.startswith("@"):
        return None

    try:
        raw = str(Decimal(raw.replace(",", "")).to_integral_value())
    except (InvalidOperation, ValueError):
        pass

    digits = re.sub(r"[^0-9]", "", raw)
    if len(digits) < 5 or len(digits) > 18:
        return None
    return digits


def normalize_username(value: str) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.startswith("@"):
        raw = raw[1:]
    username = re.sub(r"[^A-Za-z0-9_]", "", raw)
    return f"@{username}" if username else None


def normalize_invite_link(value: str) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    match = _INVITE_LINK_RE.search(raw)
    if match:
        return match.group(0)
    if raw.lower().startswith("https://t.me/") or raw.lower().startswith("http://t.me/"):
        return raw
    return None


class InviteByNumberManager:
    """Owns at most one in-flight invite-link send job."""

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
        recipients: List[InviteRecipient],
        sender_links: List[InviteSenderLink],
        *,
        max_per_account: int = 40,
        delay_min_sec: float = 1.0,
        delay_max_sec: float = 10.0,
        max_flood_wait_sec: float = 500.0,
        message_template: str = "{invite_link}",
    ) -> str:
        if self.is_running:
            raise InviteByNumberAlreadyRunningError("An invite-by-number job is already running.")

        normalized: List[InviteRecipient] = []
        seen: set[str] = set()
        for item in recipients:
            raw_id = (item.recipient_id or "").strip()
            username = normalize_username(item.username or "")
            if raw_id.startswith("@"):
                username = username or normalize_username(raw_id)
                recipient_id = ""
            else:
                recipient_id = normalize_recipient_id(raw_id) or ""
            phone = normalize_phone(item.phone or "")
            if not recipient_id and not username and not phone:
                continue
            key = recipient_id or username or phone or ""
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                InviteRecipient(
                    recipient_id=recipient_id,
                    username=username,
                    phone=phone,
                )
            )
        if not normalized:
            raise ValueError("No valid recipients provided.")

        links: List[InviteSenderLink] = []
        for item in sender_links:
            sender = normalize_phone(item.sender_phone)
            invite = normalize_invite_link(item.invite_link)
            if sender and invite:
                if self._phone_key(sender) not in self._accounts_by_phone:
                    raise ValueError(f"Sender account not found: {sender}")
                links.append(InviteSenderLink(sender_phone=sender, invite_link=invite))
        if not links:
            raise ValueError("No valid sender/invite-link pairs provided.")

        max_per_account = max(1, int(max_per_account))
        delay_min_sec = max(0.0, float(delay_min_sec))
        delay_max_sec = max(delay_min_sec, float(delay_max_sec))
        max_flood_wait_sec = max(0.0, float(max_flood_wait_sec))
        template = message_template or "{invite_link}"

        try:
            self._pool_guard.try_acquire("invite_by_number")
        except PoolBusyError as exc:
            raise InviteByNumberAlreadyRunningError(str(exc)) from exc

        job_id = uuid.uuid4().hex[:12]
        shutdown_event = asyncio.Event()
        results: List[InviteResultRow] = []
        per_account_counts: Dict[str, int] = {link.sender_phone: 0 for link in links}
        link_index = 0
        for recipient in normalized:
            assigned: Optional[InviteSenderLink] = None
            for _ in range(len(links)):
                candidate = links[link_index % len(links)]
                link_index += 1
                if per_account_counts[candidate.sender_phone] < max_per_account:
                    assigned = candidate
                    per_account_counts[candidate.sender_phone] += 1
                    break
            display_id = recipient.recipient_id or recipient.username or recipient.phone or "?"
            if assigned is None:
                results.append(
                    InviteResultRow(
                        recipient_id=display_id,
                        sender_phone="",
                        invite_link="",
                        username=recipient.username,
                        phone=recipient.phone,
                        state="skipped",
                        message="Skipped: all senders reached max_per_account.",
                    )
                )
                continue
            results.append(
                InviteResultRow(
                    recipient_id=display_id,
                    sender_phone=assigned.sender_phone,
                    invite_link=assigned.invite_link,
                    username=recipient.username,
                    phone=recipient.phone,
                    state="pending",
                    message="Queued",
                )
            )

        run = _Run(job_id=job_id, shutdown_event=shutdown_event, results=results)
        logger.info(
            "Invite-by-number job %s queued %d recipient(s) across %d sender link(s)",
            job_id,
            len(results),
            len(links),
        )

        async def _runner() -> None:
            try:
                await self._execute(
                    run,
                    delay_min_sec=delay_min_sec,
                    delay_max_sec=delay_max_sec,
                    max_flood_wait_sec=max_flood_wait_sec,
                    message_template=template,
                )
            except Exception as exc:
                logger.exception("Invite-by-number job %s failed", job_id)
                run.error = str(exc)
            finally:
                run.finished = True
                self._pool_guard.release("invite_by_number")

        run.task = asyncio.create_task(_runner(), name=f"api-invite-by-number-{job_id}")
        self._run = run
        return job_id

    async def stop(self) -> None:
        if self._run is None or self._run.task is None:
            return
        self._run.shutdown_event.set()
        await self._run.task

    def status(self) -> dict:
        if self._run is None:
            return {"running": False}
        return {
            "running": not self._run.finished,
            "job_id": self._run.job_id,
            "total": len(self._run.results),
            "sent": self._run.sent,
            "failed": self._run.failed,
            "per_account": dict(self._run.per_account),
            "finished": self._run.finished,
            "error": self._run.error,
            "results": [
                {
                    "recipient_id": row.recipient_id,
                    "sender_phone": row.sender_phone,
                    "invite_link": row.invite_link,
                    "state": row.state,
                    "message": row.message,
                }
                for row in self._run.results
            ],
        }

    async def _execute(
        self,
        run: _Run,
        *,
        delay_min_sec: float,
        delay_max_sec: float,
        max_flood_wait_sec: float,
        message_template: str,
    ) -> None:
        clients: Dict[str, object] = {}
        dead_senders: set[str] = set()
        try:
            for row in run.results:
                if run.shutdown_event.is_set():
                    if row.state == "pending":
                        row.state = "skipped"
                        row.message = "Stopped before send."
                    continue
                if row.state != "pending":
                    if row.state == "skipped":
                        run.failed += 1
                    continue
                if row.sender_phone in dead_senders:
                    row.state = "failed"
                    row.message = "Sender unavailable (previous FloodWait/PeerFlood)."
                    run.failed += 1
                    continue

                row.state = "sending"
                row.message = f"Sending invite link from {row.sender_phone}"
                recipient = InviteRecipient(
                    recipient_id=row.recipient_id if row.recipient_id.isdigit() else "",
                    username=row.username,
                    phone=row.phone,
                )
                # Preserve username/phone-only keys stored in recipient_id.
                if not recipient.recipient_id and row.recipient_id.startswith("@"):
                    recipient.username = row.recipient_id
                if not recipient.recipient_id and not recipient.username and row.phone:
                    recipient.phone = row.phone

                try:
                    client = await self._get_client(clients, row.sender_phone)
                    text = message_template.replace("{invite_link}", row.invite_link)
                    if "{invite_link}" not in message_template and row.invite_link not in text:
                        text = f"{text}\n{row.invite_link}".strip()
                    detail = await self._send_invite(
                        client,
                        recipient,
                        text,
                        sender_phone=row.sender_phone,
                    )
                    row.state = "sent"
                    row.message = detail
                    run.sent += 1
                    run.per_account[row.sender_phone] = run.per_account.get(row.sender_phone, 0) + 1
                except FloodWaitError as exc:
                    if exc.seconds > max_flood_wait_sec:
                        dead_senders.add(row.sender_phone)
                        row.state = "failed"
                        row.message = (
                            f"FloodWait {exc.seconds}s exceeds max timeout "
                            f"{max_flood_wait_sec:.0f}s"
                        )
                        run.failed += 1
                    else:
                        row.message = f"FloodWait {exc.seconds}s — waiting"
                        try:
                            await asyncio.wait_for(
                                run.shutdown_event.wait(),
                                timeout=float(exc.seconds),
                            )
                            row.state = "skipped"
                            row.message = "Stopped during FloodWait."
                            run.failed += 1
                            continue
                        except asyncio.TimeoutError:
                            pass
                        try:
                            client = await self._get_client(clients, row.sender_phone)
                            text = message_template.replace("{invite_link}", row.invite_link)
                            detail = await self._send_invite(
                                client,
                                recipient,
                                text,
                                sender_phone=row.sender_phone,
                            )
                            row.state = "sent"
                            row.message = f"{detail} (after FloodWait)"
                            run.sent += 1
                            run.per_account[row.sender_phone] = (
                                run.per_account.get(row.sender_phone, 0) + 1
                            )
                        except Exception as retry_exc:
                            row.state = "failed"
                            row.message = f"{type(retry_exc).__name__}: {retry_exc}"
                            run.failed += 1
                except PeerFloodError as exc:
                    dead_senders.add(row.sender_phone)
                    row.state = "failed"
                    row.message = f"PeerFlood: {exc}"
                    run.failed += 1
                except UserPrivacyRestrictedError:
                    row.state = "failed"
                    row.message = "User privacy settings prevent messaging."
                    run.failed += 1
                except Exception as exc:
                    row.state = "failed"
                    row.message = f"{type(exc).__name__}: {exc}"
                    run.failed += 1
                    logger.warning(
                        "Invite send failed %s -> %s: %s",
                        row.sender_phone,
                        row.recipient_id,
                        exc,
                    )

                if run.shutdown_event.is_set():
                    continue
                delay = random.uniform(delay_min_sec, delay_max_sec)
                if delay > 0:
                    try:
                        await asyncio.wait_for(run.shutdown_event.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        pass
        finally:
            await self._disconnect_all(clients)

    async def _get_client(self, clients: Dict[str, object], phone: str):
        existing = clients.get(phone)
        if existing is not None:
            return existing

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
        clients[phone] = client
        logger.info("Invite-by-number connected sender %s", phone)
        return client

    async def _disconnect_all(self, clients: Dict[str, object]) -> None:
        for phone, client in list(clients.items()):
            try:
                if getattr(client, "is_connected", lambda: False)():
                    await client.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting invite sender %s: %s", phone, exc)
            account = self._accounts_by_phone.get(self._phone_key(phone))
            if account is not None and self._session_encryption_key is not None:
                from src.accounts.session_crypto import ensure_encrypted

                ensure_encrypted(account.session_path, self._session_encryption_key)
        clients.clear()

    @staticmethod
    async def _send_invite(
        client,
        recipient: InviteRecipient,
        text: str,
        *,
        sender_phone: str,
    ) -> str:
        me = await client.get_me()
        user = await InviteByNumberManager._resolve_recipient(
            client,
            recipient,
            sender_phone=sender_phone,
            me_id=int(me.id),
        )
        sent = await client.send_message(user, text)
        message = sent[-1] if isinstance(sent, list) else sent
        peer = getattr(message, "peer_id", None)
        if not isinstance(peer, PeerUser):
            raise RuntimeError(
                f"Outgoing message peer is {type(peer).__name__}, not a user DM"
            )
        if peer.user_id == me.id:
            raise RuntimeError("Message went to Saved Messages (self), not the recipient")
        if recipient.recipient_id and peer.user_id != int(recipient.recipient_id):
            raise RuntimeError(
                f"Peer mismatch: wanted id={recipient.recipient_id}, got id={peer.user_id}"
            )

        uname = getattr(user, "username", None)
        detail = f"Delivered DM to id={peer.user_id}"
        if uname:
            detail += f" @{uname}"
        detail += f" from {sender_phone}"
        logger.info("Invite-by-number %s", detail)
        return detail

    @staticmethod
    async def _resolve_recipient(
        client,
        recipient: InviteRecipient,
        *,
        sender_phone: str,
        me_id: int,
    ) -> User:
        errors: List[str] = []

        if recipient.username:
            try:
                entity = await client.get_entity(recipient.username)
                user = InviteByNumberManager._as_user(entity, me_id)
                if recipient.recipient_id and str(user.id) != recipient.recipient_id:
                    raise LookupError(
                        f"Username {recipient.username} resolved to id={user.id}, "
                        f"expected {recipient.recipient_id}"
                    )
                return user
            except Exception as exc:
                errors.append(f"username:{exc}")

        if recipient.recipient_id:
            try:
                entity = await client.get_entity(int(recipient.recipient_id))
                return InviteByNumberManager._as_user(entity, me_id)
            except Exception as exc:
                errors.append(f"id:{exc}")

        phone = recipient.phone
        if phone and InviteByNumberManager._phone_key(phone) != InviteByNumberManager._phone_key(
            sender_phone
        ):
            try:
                return await InviteByNumberManager._resolve_by_phone(client, phone, me_id)
            except Exception as exc:
                errors.append(f"phone:{exc}")
        elif phone:
            errors.append("phone:skipped (same as sender)")

        raise LookupError(
            "Could not resolve recipient "
            f"id={recipient.recipient_id!r} username={recipient.username!r} "
            f"phone={recipient.phone!r}: {'; '.join(errors) if errors else 'no methods'}"
        )

    @staticmethod
    def _as_user(entity, me_id: int) -> User:
        if not isinstance(entity, User):
            raise LookupError(
                f"Resolved entity is {type(entity).__name__}, expected User"
            )
        if entity.id == me_id:
            raise LookupError("Resolved entity is the sender account itself")
        if getattr(entity, "bot", False):
            raise LookupError("Resolved entity is a bot")
        if getattr(entity, "deleted", False):
            raise LookupError("Resolved entity is a deleted account")
        return entity

    @staticmethod
    async def _resolve_by_phone(client, phone: str, me_id: int) -> User:
        contact = InputPhoneContact(
            client_id=random.randrange(1, 2**31 - 1),
            phone=phone,
            first_name=phone,
            last_name="",
        )
        result = await client(ImportContactsRequest([contact]))
        users = [u for u in (getattr(result, "users", None) or []) if isinstance(u, User)]
        if not users:
            raise LookupError(f"ImportContacts found no user for {phone}")
        user = InviteByNumberManager._as_user(users[0], me_id)
        try:
            await client(DeleteContactsRequest(id=[user]))
        except Exception:
            logger.debug("Could not delete temporary contact for %s", phone)
        return user
