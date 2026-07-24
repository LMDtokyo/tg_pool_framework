"""Send Telegram messages to phone-number recipients via saved Telethon sessions."""

from __future__ import annotations

import asyncio
import logging
import random
import re
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from telethon.errors import FloodWaitError, PeerFloodError, UserPrivacyRestrictedError
from telethon.tl.functions.contacts import DeleteContactsRequest, ImportContactsRequest
from telethon.tl.functions.messages import DeleteHistoryRequest
from telethon.tl.types import InputPhoneContact, PeerUser, User

from src.accounts.connection_manager import ClientFactory
from src.api.pool_guard import PoolAccessGuard, PoolBusyError
from src.config import AccountConfig

logger = logging.getLogger(__name__)


class SendByNumbersAlreadyRunningError(RuntimeError):
    """Raised when a send-by-numbers job is already in flight."""


@dataclass
class SendByNumbersResultRow:
    recipient_phone: str
    sender_phone: str = ""
    state: str = "pending"
    message: str = ""
    first_name: str = ""
    last_name: str = ""
    bio: str = ""


@dataclass
class _Run:
    job_id: str
    shutdown_event: asyncio.Event
    results: List[SendByNumbersResultRow]
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


class SendByNumbersManager:
    """Owns at most one in-flight phone-number DM job."""

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
        phone_numbers: List[str],
        message: str,
        sender_phones: Optional[List[str]] = None,
        sms_per_account_min: int = 1,
        sms_per_account_max: int = 40,
        delay_min_sec: float = 1.0,
        delay_max_sec: float = 10.0,
        max_flood_wait_sec: float = 500.0,
        delete_dialog: bool = False,
        silent: bool = False,
        link_preview: bool = True,
        request_profile: bool = False,
        pin_message: bool = False,
        use_base_data: bool = False,
        auto_repost: bool = False,
        video_note: bool = False,
        self_destruct_sec: Optional[int] = None,
        sending_by_time: bool = False,
        streams_control: bool = False,
        auto_stop: bool = False,
    ) -> str:
        if self.is_running:
            raise SendByNumbersAlreadyRunningError("A send-by-numbers job is already running.")
        if not message.strip():
            raise ValueError("Message text is required.")

        recipients: List[str] = []
        seen_recipients: set[str] = set()
        for raw in phone_numbers:
            phone = normalize_phone(raw)
            if phone and phone not in seen_recipients:
                recipients.append(phone)
                seen_recipients.add(phone)
        if not recipients:
            raise ValueError("No valid phone numbers provided.")

        senders = self._normalize_senders(sender_phones)
        if not senders:
            raise ValueError("No valid sender accounts available.")

        sms_per_account_min = max(1, int(sms_per_account_min))
        sms_per_account_max = max(sms_per_account_min, int(sms_per_account_max))
        delay_min_sec = max(0.0, float(delay_min_sec))
        delay_max_sec = max(delay_min_sec, float(delay_max_sec))
        max_flood_wait_sec = max(0.0, float(max_flood_wait_sec))

        try:
            self._pool_guard.try_acquire("send_by_numbers")
        except PoolBusyError as exc:
            raise SendByNumbersAlreadyRunningError(str(exc)) from exc

        assignments = self._assign_recipients(
            recipients,
            senders,
            sms_per_account_min=sms_per_account_min,
            sms_per_account_max=sms_per_account_max,
        )
        results = [
            SendByNumbersResultRow(
                recipient_phone=recipient,
                sender_phone=sender or "",
                state="pending" if sender else "skipped",
                message="Queued" if sender else "Skipped: all senders reached their limit.",
            )
            for recipient, sender in assignments
        ]

        job_id = uuid.uuid4().hex[:12]
        run = _Run(job_id=job_id, shutdown_event=asyncio.Event(), results=results)
        logger.info(
            "Send-by-numbers job %s queued %d phone(s) across %d sender(s)",
            job_id,
            len(results),
            len(senders),
        )

        async def _runner() -> None:
            try:
                await self._execute(
                    run,
                    message=message,
                    delay_min_sec=delay_min_sec,
                    delay_max_sec=delay_max_sec,
                    max_flood_wait_sec=max_flood_wait_sec,
                    delete_dialog=delete_dialog,
                    silent=silent,
                    link_preview=link_preview,
                    request_profile=request_profile,
                    pin_message=pin_message,
                    option_notes={
                        "use_base_data": use_base_data,
                        "auto_repost": auto_repost,
                        "video_note": video_note,
                        "self_destruct_sec": self_destruct_sec,
                        "sending_by_time": sending_by_time,
                        "streams_control": streams_control,
                        "auto_stop": auto_stop,
                    },
                )
            except Exception as exc:
                logger.exception("Send-by-numbers job %s failed", job_id)
                run.error = str(exc)
            finally:
                run.finished = True
                self._pool_guard.release("send_by_numbers")

        run.task = asyncio.create_task(_runner(), name=f"api-send-by-numbers-{job_id}")
        self._run = run
        return job_id

    def _normalize_senders(self, sender_phones: Optional[List[str]]) -> List[str]:
        source = sender_phones or [account.phone for account in self._accounts_by_phone.values()]
        senders: List[str] = []
        seen: set[str] = set()
        for raw in source:
            phone = normalize_phone(raw)
            if not phone:
                continue
            key = self._phone_key(phone)
            if key not in self._accounts_by_phone:
                raise ValueError(f"Sender account not found: {phone}")
            if phone not in seen:
                senders.append(phone)
                seen.add(phone)
        return senders

    @staticmethod
    def _assign_recipients(
        recipients: List[str],
        senders: List[str],
        *,
        sms_per_account_min: int,
        sms_per_account_max: int,
    ) -> List[tuple[str, Optional[str]]]:
        quotas = {
            sender: random.randint(sms_per_account_min, sms_per_account_max)
            for sender in senders
        }
        counts = {sender: 0 for sender in senders}
        assignments: List[tuple[str, Optional[str]]] = []
        sender_index = 0
        for recipient in recipients:
            assigned: Optional[str] = None
            for _ in range(len(senders)):
                sender = senders[sender_index % len(senders)]
                sender_index += 1
                if counts[sender] < quotas[sender]:
                    assigned = sender
                    counts[sender] += 1
                    break
            assignments.append((recipient, assigned))
        return assignments

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
                    "recipient_phone": row.recipient_phone,
                    "sender_phone": row.sender_phone,
                    "state": row.state,
                    "message": row.message,
                    "first_name": row.first_name,
                    "last_name": row.last_name,
                    "bio": row.bio,
                }
                for row in self._run.results
            ],
        }

    async def _execute(
        self,
        run: _Run,
        *,
        message: str,
        delay_min_sec: float,
        delay_max_sec: float,
        max_flood_wait_sec: float,
        delete_dialog: bool,
        silent: bool,
        link_preview: bool,
        request_profile: bool,
        pin_message: bool,
        option_notes: dict,
    ) -> None:
        clients: Dict[str, object] = {}
        dead_senders: set[str] = set()
        try:
            for row in run.results:
                if row.state == "skipped":
                    run.failed += 1
                    continue
                if run.shutdown_event.is_set():
                    row.state = "skipped"
                    row.message = "Stopped before send."
                    continue
                if row.sender_phone in dead_senders:
                    row.state = "failed"
                    row.message = "Sender unavailable after previous FloodWait/PeerFlood."
                    run.failed += 1
                    continue

                row.state = "sending"
                row.message = f"Resolving {row.recipient_phone}"
                try:
                    client = await self._get_client(clients, row.sender_phone)
                    detail = await self._send_to_phone(
                        client,
                        row,
                        message,
                        silent=silent,
                        link_preview=link_preview,
                        request_profile=request_profile,
                        pin_message=pin_message,
                        delete_dialog=delete_dialog,
                    )
                    row.state = "sent"
                    row.message = detail
                    run.sent += 1
                    run.per_account[row.sender_phone] = run.per_account.get(row.sender_phone, 0) + 1
                    self._append_option_note(row, option_notes)
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
                        row.message = f"FloodWait {exc.seconds}s - waiting"
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
                            detail = await self._send_to_phone(
                                client,
                                row,
                                message,
                                silent=silent,
                                link_preview=link_preview,
                                request_profile=request_profile,
                                pin_message=pin_message,
                                delete_dialog=delete_dialog,
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
                        "Send-by-numbers failed %s -> %s: %s",
                        row.sender_phone,
                        row.recipient_phone,
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

    @staticmethod
    def _append_option_note(row: SendByNumbersResultRow, option_notes: dict) -> None:
        unsupported = [
            name
            for name, enabled in option_notes.items()
            if enabled and name
            in {
                "auto_repost",
                "video_note",
                "self_destruct_sec",
                "sending_by_time",
                "streams_control",
                "auto_stop",
            }
        ]
        if unsupported:
            row.message += f" Unsupported UI option(s) ignored: {', '.join(unsupported)}."

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
        logger.info("Send-by-numbers connected sender %s", phone)
        return client

    async def _disconnect_all(self, clients: Dict[str, object]) -> None:
        for phone, client in list(clients.items()):
            try:
                if getattr(client, "is_connected", lambda: False)():
                    await client.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting sender %s: %s", phone, exc)
            account = self._accounts_by_phone.get(self._phone_key(phone))
            if account is not None and self._session_encryption_key is not None:
                from src.accounts.session_crypto import ensure_encrypted

                ensure_encrypted(account.session_path, self._session_encryption_key)
        clients.clear()

    @staticmethod
    async def _send_to_phone(
        client,
        row: SendByNumbersResultRow,
        message: str,
        *,
        silent: bool,
        link_preview: bool,
        request_profile: bool,
        pin_message: bool,
        delete_dialog: bool,
    ) -> str:
        me = await client.get_me()
        user = await SendByNumbersManager._resolve_by_phone(client, row.recipient_phone, int(me.id))
        if request_profile:
            row.first_name = getattr(user, "first_name", "") or ""
            row.last_name = getattr(user, "last_name", "") or ""

        sent = await client.send_message(
            user,
            message,
            silent=silent,
            link_preview=link_preview,
        )
        msg = sent[-1] if isinstance(sent, list) else sent
        peer = getattr(msg, "peer_id", None)
        if not isinstance(peer, PeerUser):
            raise RuntimeError(
                f"Outgoing message peer is {type(peer).__name__}, not a user DM"
            )
        if peer.user_id == me.id:
            raise RuntimeError("Message went to Saved Messages (self), not the recipient")
        if peer.user_id != user.id:
            raise RuntimeError(f"Peer mismatch: wanted id={user.id}, got id={peer.user_id}")

        if pin_message:
            try:
                await client.pin_message(user, msg, notify=False)
            except Exception as exc:
                logger.debug("Could not pin message for %s: %s", row.recipient_phone, exc)

        if delete_dialog:
            try:
                await client(DeleteHistoryRequest(peer=user, max_id=0, revoke=True))
            except Exception as exc:
                logger.debug("Could not delete dialog for %s: %s", row.recipient_phone, exc)

        uname = getattr(user, "username", None)
        detail = f"Delivered DM to {row.recipient_phone} id={user.id}"
        if uname:
            detail += f" @{uname}"
        detail += f" from {row.sender_phone}"
        return detail

    @staticmethod
    async def _resolve_by_phone(client, phone: str, me_id: int) -> User:
        errors: List[str] = []
        digits = re.sub(r"[^0-9]", "", phone)
        candidates = [phone]
        if digits:
            candidates.extend([digits, f"+{digits}"])
        candidates = list(dict.fromkeys(candidates))

        for candidate in candidates:
            try:
                entity = await client.get_entity(candidate)
                return SendByNumbersManager._as_user(entity, me_id)
            except Exception as exc:
                errors.append(f"get_entity({candidate}): {exc}")

        imported_users: List[User] = []
        for candidate in candidates:
            contact = InputPhoneContact(
                client_id=random.randrange(1, 2**31 - 1),
                phone=candidate,
                first_name=candidate,
                last_name="",
            )
            try:
                result = await client(ImportContactsRequest([contact]))
            except Exception as exc:
                errors.append(f"import({candidate}): {exc}")
                continue

            users = [
                u
                for u in (getattr(result, "users", None) or [])
                if isinstance(u, User)
            ]
            imported_users.extend(users)
            matched = SendByNumbersManager._select_imported_phone_user(
                users,
                expected_digits=digits,
                me_id=me_id,
            )
            if matched is None:
                imported_count = len(getattr(result, "imported", None) or [])
                retry_count = len(getattr(result, "retry_contacts", None) or [])
                errors.append(
                    f"import({candidate}): users={len(users)} imported={imported_count} "
                    f"retry_contacts={retry_count}"
                )
                continue

            try:
                await client(DeleteContactsRequest(id=[matched]))
            except Exception:
                logger.debug("Could not delete temporary contact for %s", phone)
            return matched

        if imported_users:
            errors.append("import returned users, but none matched the requested phone")
        raise LookupError(
            f"Could not resolve Telegram user for {phone}. The number may exist, but "
            "Telegram did not allow this sender account to discover it by phone. "
            "Try a sender account that already has this contact, or send by username "
            "if the recipient has one. Details: "
            + "; ".join(errors[-4:])
        )

    @staticmethod
    def _select_imported_phone_user(
        users: List[User],
        *,
        expected_digits: str,
        me_id: int,
    ) -> Optional[User]:
        fallback: Optional[User] = None
        for entity in users:
            try:
                user = SendByNumbersManager._as_user(entity, me_id)
            except LookupError:
                continue
            user_phone = re.sub(r"[^0-9]", "", getattr(user, "phone", "") or "")
            if user_phone and user_phone == expected_digits:
                return user
            fallback = fallback or user
        return fallback

    @staticmethod
    def _as_user(entity, me_id: int) -> User:
        if not isinstance(entity, User):
            raise LookupError(f"Resolved entity is {type(entity).__name__}, expected User")
        if entity.id == me_id:
            raise LookupError("Resolved entity is the sender account itself")
        if getattr(entity, "bot", False):
            raise LookupError("Resolved entity is a bot")
        if getattr(entity, "deleted", False):
            raise LookupError("Resolved entity is a deleted account")
        return entity
