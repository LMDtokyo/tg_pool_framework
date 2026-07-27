"""Resumable Telegram phone-number checker backed by a local SQLite database."""

from __future__ import annotations

import asyncio
import io
import logging
import random
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    PeerFloodError,
    UserDeactivatedBanError,
)
from telethon.tl.functions.contacts import DeleteContactsRequest, ImportContactsRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import (
    InputPhoneContact,
    User,
    UserStatusEmpty,
    UserStatusLastMonth,
    UserStatusLastWeek,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)

from src.accounts.connection_manager import ClientFactory
from src.api.pool_guard import PoolAccessGuard, PoolBusyError
from src.config import AccountConfig

logger = logging.getLogger(__name__)


class NumberCheckerAlreadyRunningError(RuntimeError):
    """Raised when another checker job already owns the account pool."""


class _StopRequested(RuntimeError):
    """Internal signal for interruptible waits."""


@dataclass
class NumberCheckRow:
    phone: str
    state: str = "pending"
    account_phone: str = ""
    telegram_id: str = ""
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    bio: str = ""
    online_status: str = ""
    last_seen: str = ""
    gender: str = ""
    message: str = "Queued"
    checked_at: str = ""


@dataclass(frozen=True)
class NumberCheckerOptions:
    request_profile_data: bool
    gender_detection: bool
    delay_min_sec: float
    delay_max_sec: float
    max_flood_wait_sec: float
    requests_per_account: int
    streams: int
    stream_delay_min_sec: float
    stream_delay_max_sec: float
    remove_imported_contacts: bool
    results_dir: str


_RESULT_COLUMNS = {
    "Phone": "phone",
    "Status": "state",
    "Telegram ID": "telegram_id",
    "Username": "username",
    "First name": "first_name",
    "Last name": "last_name",
    "Bio": "bio",
    "Online status": "online_status",
    "Last seen": "last_seen",
    "Gender": "gender",
    "Account": "account_phone",
    "Details": "message",
    "Checked at": "checked_at",
}
_USAGE_COLUMNS = ["Day", "Account", "Count"]


@dataclass
class _Run:
    job_id: str
    result_path: str
    phone_numbers: List[str]
    shutdown_event: asyncio.Event
    task: Optional[asyncio.Task] = None
    finished: bool = False
    error: Optional[str] = None
    found: int = 0
    not_found: int = 0
    failed: int = 0
    per_account: Dict[str, int] = field(default_factory=dict)
    export_path: Optional[str] = None


def normalize_phone(value: str) -> Optional[str]:
    """Remove formatting while intentionally preserving every supplied digit."""
    digits = re.sub(r"[^0-9]", "", value or "")
    if len(digits) < 7 or len(digits) > 16:
        return None
    return f"+{digits}"


_FEMALE_NAMES = {
    "alice", "anna", "anastasia", "alina", "alexandra", "catherine", "daria",
    "diana", "elena", "elizabeth", "emily", "emma", "irina", "jane", "julia",
    "katerina", "ksenia", "laura", "maria", "marina", "natalia", "olga",
    "polina", "sofia", "sophia", "tatiana", "valeria", "victoria", "yulia",
    "александра", "алина", "анастасия", "анна", "валерия", "виктория", "дарья",
    "диана", "екатерина", "елена", "ирина", "ксения", "марина", "мария",
    "наталья", "ольга", "полина", "софия", "татьяна", "юлия",
}
_MALE_NAMES = {
    "alex", "alexander", "andrew", "anton", "artem", "arthur", "daniel",
    "david", "denis", "dmitry", "george", "ivan", "james", "john", "kirill",
    "maxim", "michael", "nikita", "nicolas", "oleg", "pavel", "peter", "roman",
    "sergey", "thomas", "timur", "victor", "vladimir", "yuri",
    "александр", "алексей", "андрей", "антон", "артем", "артём", "виктор",
    "владимир", "даниил", "денис", "дмитрий", "иван", "кирилл", "максим",
    "михаил", "никита", "олег", "павел", "роман", "сергей", "тимур", "юрий",
}


def infer_gender(first_name: str) -> str:
    """Best-effort name-based classification; unknown is preferable to a bad guess."""
    name = re.sub(r"[^\w'-]", "", (first_name or "").strip().casefold())
    if not name:
        return "unknown"
    if name in _FEMALE_NAMES:
        return "female"
    if name in _MALE_NAMES:
        return "male"
    if name.endswith(("а", "я")) and not name.endswith(("иля", "никита")):
        return "female"
    if name.endswith(("a", "ia", "ie")):
        return "female"
    return "unknown"


def _presence(user: User) -> tuple[str, str]:
    status = getattr(user, "status", None)
    if isinstance(status, UserStatusOnline):
        expires = getattr(status, "expires", None)
        return "online", _iso(expires)
    if isinstance(status, UserStatusOffline):
        return "offline", _iso(getattr(status, "was_online", None))
    if isinstance(status, UserStatusRecently):
        return "recently", ""
    if isinstance(status, UserStatusLastWeek):
        return "last_week", ""
    if isinstance(status, UserStatusLastMonth):
        return "last_month", ""
    if isinstance(status, UserStatusEmpty) or status is None:
        return "unknown", ""
    return type(status).__name__.removeprefix("UserStatus").casefold(), ""


def _iso(value) -> str:
    if not isinstance(value, datetime):
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _user_with_id(users, user_id: int) -> Optional[User]:
    return next(
        (
            user
            for user in (users or [])
            if isinstance(user, User)
            and not getattr(user, "deleted", False)
            and int(getattr(user, "id", 0) or 0) == user_id
        ),
        None,
    )


def _select_imported_user(imported, client_id: int, target: str) -> Optional[User]:
    """Select the user Telegram mapped to this exact imported contact."""
    mappings = getattr(imported, "imported", None) or []
    mapped_user_id = next(
        (
            int(getattr(item, "user_id", 0) or 0)
            for item in mappings
            if int(getattr(item, "client_id", 0) or 0) == client_id
        ),
        0,
    )
    users = getattr(imported, "users", None) or []
    if mapped_user_id:
        return _user_with_id(users, mapped_user_id)

    target_digits = re.sub(r"[^0-9]", "", target or "")
    phone_matches = [
        user
        for user in users
        if isinstance(user, User)
        and not getattr(user, "deleted", False)
        and re.sub(r"[^0-9]", "", getattr(user, "phone", "") or "")
        == target_digits
    ]
    if len(phone_matches) == 1:
        return phone_matches[0]
    return users[0] if len(users) == 1 and isinstance(users[0], User) else None


class NumberCheckerManager:
    """Owns one cancellable checker job and persists progress after every lookup."""

    def __init__(
        self,
        accounts: List[AccountConfig],
        pool_guard: PoolAccessGuard,
        session_encryption_key: Optional[bytes] = None,
        usage_database_path: Optional[str] = None,
    ) -> None:
        self._accounts_by_phone = {self._phone_key(a.phone): a for a in accounts}
        self._pool_guard = pool_guard
        self._session_encryption_key = session_encryption_key
        self._run: Optional[_Run] = None
        self._storage_lock = threading.RLock()

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
        phone_numbers: Optional[List[str]] = None,
        database_path: Optional[str] = None,
        sender_phones: Optional[List[str]] = None,
        request_profile_data: bool = False,
        gender_detection: bool = False,
        delay_min_sec: float = 5.0,
        delay_max_sec: float = 10.0,
        max_flood_wait_sec: float = 500.0,
        requests_per_account: int = 8,
        streams: int = 1,
        stream_delay_min_sec: float = 30.0,
        stream_delay_max_sec: float = 45.0,
        remove_imported_contacts: bool = True,
        results_dir: str = "exports",
    ) -> str:
        if self.is_running:
            raise NumberCheckerAlreadyRunningError("A number-checker job is already running.")

        senders = self._normalize_senders(sender_phones)
        if not senders:
            raise ValueError("No valid checker accounts available.")

        normalized: List[str] = []
        seen: set[str] = set()
        for raw in phone_numbers or []:
            phone = normalize_phone(raw)
            if phone and phone not in seen:
                seen.add(phone)
                normalized.append(phone)

        output_dir = Path(results_dir or "exports").expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        if normalized:
            result_path = output_dir / "number_checker.xlsx"
        elif database_path:
            result_path = Path(database_path).expanduser()
            if result_path.suffix.casefold() != ".xlsx" or not result_path.is_file():
                raise ValueError("Select an existing number_checker.xlsx workbook.")
        else:
            raise ValueError("No valid phone numbers provided.")

        delay_min = max(0.0, float(delay_min_sec))
        delay_max = max(delay_min, float(delay_max_sec))
        stream_delay_min = max(0.0, float(stream_delay_min_sec))
        stream_delay_max = max(stream_delay_min, float(stream_delay_max_sec))
        request_limit = int(requests_per_account)
        if request_limit < 1 or request_limit > 20:
            raise ValueError("Requests per account must be between 1 and 20.")
        options = NumberCheckerOptions(
            request_profile_data=bool(request_profile_data),
            gender_detection=bool(gender_detection),
            delay_min_sec=delay_min,
            delay_max_sec=delay_max,
            max_flood_wait_sec=max(0.0, float(max_flood_wait_sec)),
            requests_per_account=request_limit,
            streams=max(1, min(int(streams), len(senders))),
            stream_delay_min_sec=stream_delay_min,
            stream_delay_max_sec=stream_delay_max,
            remove_imported_contacts=bool(remove_imported_contacts),
            results_dir=str(output_dir),
        )

        self._initialize_results(result_path, normalized)
        pending = self._pending_phones(result_path)
        if not pending:
            raise ValueError("The checker workbook has no unfinished phone numbers.")

        try:
            self._pool_guard.try_acquire("number_checker")
        except PoolBusyError as exc:
            raise NumberCheckerAlreadyRunningError(str(exc)) from exc

        job_id = uuid.uuid4().hex[:12]
        run = _Run(
            job_id=job_id,
            result_path=str(result_path.resolve()),
            phone_numbers=pending,
            shutdown_event=asyncio.Event(),
        )

        async def _runner() -> None:
            try:
                await self._run_job(run, pending, senders, options)
            except Exception as exc:
                logger.exception("Number-checker job %s failed", job_id)
                run.error = str(exc)
            finally:
                run.export_path = run.result_path
                run.finished = True
                self._pool_guard.release("number_checker")

        run.task = asyncio.create_task(_runner(), name=f"api-number-checker-{job_id}")
        self._run = run
        return job_id

    def _normalize_senders(self, sender_phones: Optional[List[str]]) -> List[str]:
        source = sender_phones or [a.phone for a in self._accounts_by_phone.values()]
        result: List[str] = []
        seen: set[str] = set()
        for phone in source:
            key = self._phone_key(phone)
            if not key or key in seen:
                continue
            if key not in self._accounts_by_phone:
                raise ValueError(f"Checker account not found: {phone}")
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
        active = set(run.phone_numbers)
        rows = [
            row for row in self._read_rows(Path(run.result_path))
            if row.phone in active
        ]
        pending = sum(row.state == "pending" for row in rows)
        return {
            "running": not run.finished,
            "job_id": run.job_id,
            "database_path": None,
            "export_path": run.export_path,
            "total": len(rows),
            "found": sum(row.state == "found" for row in rows),
            "not_found": sum(row.state == "not_found" for row in rows),
            "failed": sum(row.state == "failed" for row in rows),
            "pending": pending,
            "per_account": dict(run.per_account),
            "finished": run.finished,
            "error": run.error,
            "results": [row.__dict__.copy() for row in rows],
        }

    async def _run_job(
        self,
        run: _Run,
        pending: List[str],
        senders: List[str],
        options: NumberCheckerOptions,
    ) -> None:
        assignments: Dict[str, List[str]] = {phone: [] for phone in senders}
        remaining_capacity: Dict[str, int] = {}
        for sender in senders:
            used = self._daily_usage(sender, Path(run.result_path))
            remaining_capacity[sender] = max(0, options.requests_per_account - used)

        sender_index = 0
        for target in pending:
            assigned = False
            for _ in range(len(senders)):
                sender = senders[sender_index % len(senders)]
                sender_index += 1
                if remaining_capacity[sender] <= 0:
                    continue
                assignments[sender].append(target)
                remaining_capacity[sender] -= 1
                assigned = True
                break
            if not assigned:
                break

        work = [(phone, items) for phone, items in assignments.items() if items]
        if not work:
            run.error = "All selected accounts reached their daily request limit."
            return

        semaphore = asyncio.Semaphore(options.streams)

        async def worker(index: int, sender: str, targets: List[str]) -> None:
            async with semaphore:
                try:
                    if index >= options.streams and options.stream_delay_max_sec > 0:
                        await self._interruptible_wait(
                            run,
                            random.uniform(
                                options.stream_delay_min_sec,
                                options.stream_delay_max_sec,
                            ),
                        )
                    await self._run_account(run, sender, targets, options)
                except _StopRequested:
                    return

        await asyncio.gather(
            *(worker(index, sender, targets) for index, (sender, targets) in enumerate(work))
        )

        if self._pending_phones(Path(run.result_path)) and not run.shutdown_event.is_set():
            run.error = (
                "Selected accounts reached their daily request limit; "
                "unfinished numbers remain in number_checker.xlsx for the next run."
            )

    async def _run_account(
        self,
        run: _Run,
        sender: str,
        targets: List[str],
        options: NumberCheckerOptions,
    ) -> None:
        client = None
        try:
            client = await self._connect(sender)
            for target in targets:
                if run.shutdown_event.is_set():
                    break
                self._set_checking(Path(run.result_path), target, sender)
                try:
                    row = await self._check_with_flood_wait(
                        run, client, target, sender, options
                    )
                except _StopRequested:
                    self._set_pending(Path(run.result_path), target, "Stopped before completion.")
                    break
                except FloodWaitError as exc:
                    self._set_pending(
                        Path(run.result_path),
                        target,
                        f"Account paused: FloodWait {exc.seconds}s exceeds maximum timeout.",
                    )
                    break
                except (UserDeactivatedBanError, AuthKeyUnregisteredError, PeerFloodError) as exc:
                    self._set_pending(
                        Path(run.result_path),
                        target,
                        f"Account paused: {type(exc).__name__}.",
                    )
                    break
                except Exception as exc:
                    row = NumberCheckRow(
                        phone=target,
                        state="failed",
                        account_phone=sender,
                        message=f"{type(exc).__name__}: {exc}",
                    )
                    logger.warning("Number check failed %s via %s: %s", target, sender, exc)

                self._save_row(Path(run.result_path), row)
                if row.state in {"found", "not_found"}:
                    self._increment_daily_usage(sender, Path(run.result_path))
                    run.per_account[sender] = run.per_account.get(sender, 0) + 1
                if row.state == "found":
                    run.found += 1
                elif row.state == "not_found":
                    run.not_found += 1
                else:
                    run.failed += 1

                if not run.shutdown_event.is_set():
                    try:
                        await self._interruptible_wait(
                            run,
                            random.uniform(options.delay_min_sec, options.delay_max_sec),
                        )
                    except _StopRequested:
                        break
        except _StopRequested:
            pass
        except Exception as exc:
            logger.warning("Checker account unavailable %s: %s", sender, exc)
            for target in targets:
                self._set_pending(
                    Path(run.result_path),
                    target,
                    f"Account unavailable: {type(exc).__name__}: {exc}",
                    only_if_unfinished=True,
                )
        finally:
            if client is not None:
                await self._disconnect(sender, client)

    async def _check_with_flood_wait(
        self,
        run: _Run,
        client,
        target: str,
        sender: str,
        options: NumberCheckerOptions,
    ) -> NumberCheckRow:
        while True:
            try:
                return await self._check_one(client, target, sender, options)
            except FloodWaitError as exc:
                if exc.seconds > options.max_flood_wait_sec:
                    raise
                self._set_pending(
                    Path(run.result_path),
                    target,
                    f"FloodWait {exc.seconds}s; resuming automatically.",
                )
                await self._interruptible_wait(run, float(exc.seconds))
                self._set_checking(Path(run.result_path), target, sender)

    async def _check_one(
        self,
        client,
        target: str,
        sender: str,
        options: NumberCheckerOptions,
    ) -> NumberCheckRow:
        client_id = random.randrange(1, 2**63 - 1)
        contact = InputPhoneContact(
            client_id=client_id,
            phone=target,
            first_name=target,
            last_name="",
        )
        imported = await client(ImportContactsRequest([contact]))
        user = _select_imported_user(imported, client_id, target)
        if user is None:
            return NumberCheckRow(
                phone=target,
                state="not_found",
                account_phone=sender,
                message="Number not found",
            )

        temporary_contact = any(
            int(getattr(item, "client_id", 0) or 0) == client_id
            for item in (getattr(imported, "imported", None) or [])
        )
        contact_removed = False
        try:
            profile_user = user
            bio = ""
            if options.request_profile_data:
                # Telegram may expose the locally imported contact alias while the
                # phone remains in the account's contacts. Remove the temporary
                # contact first, then use the fresh user returned by Telegram.
                if options.remove_imported_contacts and temporary_contact:
                    deleted = await client(DeleteContactsRequest(id=[user]))
                    contact_removed = True
                    profile_user = (
                        _user_with_id(
                            getattr(deleted, "users", None),
                            int(getattr(user, "id", 0) or 0),
                        )
                        or profile_user
                    )
                full = await client(GetFullUserRequest(user))
                profile_user = (
                    _user_with_id(
                        getattr(full, "users", None),
                        int(getattr(user, "id", 0) or 0),
                    )
                    or profile_user
                )
                bio = (
                    getattr(getattr(full, "full_user", None), "about", None) or ""
                ).strip()

            first_name = (getattr(profile_user, "first_name", None) or "").strip()
            last_name = (getattr(profile_user, "last_name", None) or "").strip()
            online_status, last_seen = _presence(profile_user)
            return NumberCheckRow(
                phone=target,
                state="found",
                account_phone=sender,
                telegram_id=str(getattr(profile_user, "id", "") or ""),
                username=(getattr(profile_user, "username", None) or "").strip(),
                first_name=first_name if options.request_profile_data else "",
                last_name=last_name if options.request_profile_data else "",
                bio=bio,
                online_status=online_status,
                last_seen=last_seen,
                gender=infer_gender(first_name) if options.gender_detection else "",
                message="User found",
            )
        finally:
            if (
                options.remove_imported_contacts
                and temporary_contact
                and not contact_removed
            ):
                try:
                    await client(DeleteContactsRequest(id=[user]))
                except Exception as exc:
                    logger.debug("Could not remove temporary contact %s: %s", target, exc)

    async def _interruptible_wait(self, run: _Run, seconds: float) -> None:
        if seconds <= 0:
            if run.shutdown_event.is_set():
                raise _StopRequested
            return
        try:
            await asyncio.wait_for(run.shutdown_event.wait(), timeout=seconds)
            raise _StopRequested
        except asyncio.TimeoutError:
            return

    async def _connect(self, phone: str):
        account = self._accounts_by_phone.get(self._phone_key(phone))
        if account is None:
            raise ValueError(f"Checker account not found: {phone}")
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

    def _initialize_results(self, path: Path, phones: List[str]) -> None:
        """Merge input into the single cumulative workbook and queue it for checking."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._storage_lock:
            rows, usage = self._load_workbook(path)
            by_phone = {row.phone: row for row in rows}

            for row in rows:
                if row.state in {"checking", "waiting"}:
                    row.state = "pending"
                    row.message = "Interrupted; queued to resume"

            for phone in phones:
                row = by_phone.get(phone)
                if row is None:
                    row = NumberCheckRow(phone=phone)
                    rows.append(row)
                    by_phone[phone] = row
                else:
                    row.state = "pending"
                    row.account_phone = ""
                    row.message = "Queued for recheck"

            self._write_workbook(path, rows, usage)

    def _pending_phones(self, path: Path) -> List[str]:
        return [row.phone for row in self._read_rows(path) if row.state == "pending"]

    def _set_checking(self, path: Path, phone: str, account_phone: str) -> None:
        with self._storage_lock:
            rows, usage = self._load_workbook(path)
            row = next((item for item in rows if item.phone == phone), None)
            if row is None:
                row = NumberCheckRow(phone=phone)
                rows.append(row)
            row.state = "checking"
            row.account_phone = account_phone
            row.message = "Checking"
            self._write_workbook(path, rows, usage)

    def _set_pending(
        self,
        path: Path,
        phone: str,
        message: str,
        *,
        only_if_unfinished: bool = False,
    ) -> None:
        with self._storage_lock:
            rows, usage = self._load_workbook(path)
            row = next((item for item in rows if item.phone == phone), None)
            if row is None:
                row = NumberCheckRow(phone=phone)
                rows.append(row)
            if not only_if_unfinished or row.state in {"pending", "checking", "waiting"}:
                row.state = "pending"
                row.message = message
                self._write_workbook(path, rows, usage)

    def _save_row(self, path: Path, row: NumberCheckRow) -> None:
        with self._storage_lock:
            rows, usage = self._load_workbook(path)
            row.checked_at = datetime.now(timezone.utc).isoformat()
            index = next(
                (index for index, item in enumerate(rows) if item.phone == row.phone),
                None,
            )
            if index is None:
                rows.append(row)
            else:
                rows[index] = row
            self._write_workbook(path, rows, usage)

    def _read_rows(self, path: Path) -> List[NumberCheckRow]:
        with self._storage_lock:
            rows, _ = self._load_workbook(path)
            return rows

    def _daily_usage(self, account_phone: str, path: Path) -> int:
        with self._storage_lock:
            _, usage = self._load_workbook(path)
            today = date.today().isoformat()
            return next(
                (
                    int(item["Count"])
                    for item in usage
                    if item["Day"] == today and item["Account"] == account_phone
                ),
                0,
            )

    def _increment_daily_usage(self, account_phone: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._storage_lock:
            rows, usage = self._load_workbook(path)
            today = date.today().isoformat()
            item = next(
                (
                    item
                    for item in usage
                    if item["Day"] == today and item["Account"] == account_phone
                ),
                None,
            )
            if item is None:
                usage.append({"Day": today, "Account": account_phone, "Count": 1})
            else:
                item["Count"] = int(item["Count"]) + 1
            self._write_workbook(path, rows, usage)

    @staticmethod
    def _load_workbook(path: Path) -> tuple[List[NumberCheckRow], List[dict]]:
        if not path.is_file():
            return [], []

        sheets = pd.read_excel(path, sheet_name=None, dtype=str, keep_default_na=False)
        if not sheets:
            return [], []
        results_frame = sheets.get("Results", next(iter(sheets.values())))
        rows: List[NumberCheckRow] = []
        seen: set[str] = set()
        for record in results_frame.to_dict(orient="records"):
            phone = normalize_phone(str(record.get("Phone", "")))
            if not phone or phone in seen:
                continue
            seen.add(phone)
            values = {
                field_name: str(record.get(column_name, "") or "").strip()
                for column_name, field_name in _RESULT_COLUMNS.items()
            }
            values["phone"] = phone
            values["state"] = values["state"] or "pending"
            values["message"] = values["message"] or "Queued"
            rows.append(NumberCheckRow(**values))

        usage: List[dict] = []
        usage_frame = sheets.get("Usage")
        if usage_frame is not None:
            for record in usage_frame.to_dict(orient="records"):
                try:
                    count = max(0, int(str(record.get("Count", "0") or "0")))
                except ValueError:
                    count = 0
                usage.append(
                    {
                        "Day": str(record.get("Day", "") or ""),
                        "Account": str(record.get("Account", "") or ""),
                        "Count": count,
                    }
                )
        return rows, usage

    @staticmethod
    def _write_workbook(path: Path, rows: List[NumberCheckRow], usage: List[dict]) -> None:
        records = [
            {
                column_name: getattr(row, field_name)
                for column_name, field_name in _RESULT_COLUMNS.items()
            }
            for row in rows
        ]
        results_frame = pd.DataFrame(records, columns=list(_RESULT_COLUMNS))
        usage_frame = pd.DataFrame(usage, columns=_USAGE_COLUMNS)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            results_frame.to_excel(writer, sheet_name="Results", index=False)
            usage_frame.to_excel(writer, sheet_name="Usage", index=False)
            results_sheet = writer.book["Results"]
            results_sheet.freeze_panes = "A2"
            results_sheet.auto_filter.ref = results_sheet.dimensions
            widths = [18, 13, 16, 20, 20, 20, 36, 18, 26, 12, 18, 38, 28]
            for index, width in enumerate(widths, start=1):
                results_sheet.column_dimensions[
                    results_sheet.cell(row=1, column=index).column_letter
                ].width = width
            writer.book["Usage"].sheet_state = "hidden"
        path.write_bytes(buffer.getvalue())

