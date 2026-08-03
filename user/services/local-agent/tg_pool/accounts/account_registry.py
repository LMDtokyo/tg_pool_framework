"""
tg_pool/account_registry.py — Thread-safe account registry with Fluent query API.

AccountRegistry:
  Aggregates AccountConfig, AccountState (from health checker), and
  ProxyState (from proxy checker) for every account in the pool.

  All mutations go through asyncio.Lock to guarantee that concurrent
  health-checker and proxy-checker coroutines cannot produce a torn read.
  Reads via snapshot() never block; they operate on a copy of the dict
  captured atomically (dict-copy is O(n) but the GIL makes it safe from
  partial-write corruption).

AccountQuery — Fluent Specification API:
  query = registry.query()
  results = (
      query
      .filter_by_status(AccountStatus.ALIVE, AccountStatus.SPAMBLOCK)
      .filter_by_premium(True)
      .filter_proxy_active(True)
      .filter_restriction_expiring_within(hours=24)
      .search("ivan")
      .sort_by("latency_ms")
      .execute()
  )

RegistryEntry:
  Immutable snapshot of one account.  Use dataclasses.replace() to
  produce updated versions; the registry always stores the latest.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

from tg_pool.config import AccountConfig, normalize_account_phone
from tg_pool.accounts.health_checker import AccountState, AccountStatus
from tg_pool.db.background_writer import SequentialWriter
from tg_pool.proxy.proxy_checker import ProxyState

if TYPE_CHECKING:
    from tg_pool.db.repository import AccountRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RegistryEntry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegistryEntry:
    """
    Immutable snapshot of a single account's current aggregated state.

    Constructed by AccountRegistry and consumed by AccountQuery / LiveMonitor.
    """
    account: AccountConfig
    state: Optional[AccountState] = None
    proxy_state: Optional[ProxyState] = None
    last_checked: Optional[datetime] = None
    first_seen: Optional[datetime] = None
    role: str = ""
    folder: str = ""


# ---------------------------------------------------------------------------
# AccountRegistry
# ---------------------------------------------------------------------------

class AccountRegistry:
    """
    Thread-safe registry of accounts and their runtime states.

    All write operations (register, update_state, update_proxy_state)
    acquire _lock to serialise mutations.  Reads via snapshot() are
    lock-free atomic copies that provide a consistent view for queries.
    """

    def __init__(self, repository: Optional["AccountRepository"] = None) -> None:
        self._entries: Dict[str, RegistryEntry] = {}
        self._lock = asyncio.Lock()
        self._repository = repository
        self._writer = SequentialWriter("registry") if repository is not None else None

    # ------------------------------------------------------------------
    # Durable store (optional — no-op if no repository was configured)
    # ------------------------------------------------------------------

    async def load_from_repository(self) -> None:
        """Populate the registry from the durable store at startup."""
        if self._repository is None:
            return
        entries = await self._repository.load_all()
        async with self._lock:
            for entry in entries:
                self._entries[entry.account.phone] = entry
        logger.info("Registry: loaded %d accounts from durable store.", len(entries))

    def _persist(self, entry: RegistryEntry) -> None:
        """Fire-and-forget durable write — a storage hiccup must never break the hot path."""
        if self._repository is None:
            return

        async def _write() -> None:
            try:
                await self._repository.upsert(entry)
            except Exception:
                logger.exception("Registry: failed to persist %s", entry.account.phone)

        assert self._writer is not None
        self._writer.submit(_write)

    async def close(self) -> None:
        """Drain pending durable writes. Safe to call more than once."""
        if self._writer is not None:
            await self._writer.close()

    # ------------------------------------------------------------------
    # Write operations (locked)
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_registration(existing: Optional[RegistryEntry], account: AccountConfig) -> RegistryEntry:
        """
        Build the entry to store for `account`, carrying forward everything
        re-registration must not clobber: first_seen, state, proxy_state,
        last_checked, role, folder. Only the AccountConfig itself is replaced.
        """
        if existing is None:
            return RegistryEntry(account=account, first_seen=datetime.now(timezone.utc))
        return replace(existing, account=account)

    async def register(self, account: AccountConfig) -> None:
        """
        Add or update an account in the registry.

        Preserves first_seen, state, proxy_state, last_checked, role, and
        folder if the phone is already known — re-registering (e.g. on every
        health-check run) must never wipe previously assigned/durable data.
        """
        async with self._lock:
            existing = self._entries.get(account.phone)
            entry = self._merge_registration(existing, account)
            self._entries[account.phone] = entry
        logger.debug("Registry: registered %s", account.phone)
        self._persist(entry)

    async def register_many(self, accounts: Sequence[AccountConfig]) -> None:
        """Bulk register a list of accounts. Preserves existing entry data for already-known phones."""
        entries: List[RegistryEntry] = []
        async with self._lock:
            for acc in accounts:
                existing = self._entries.get(acc.phone)
                entry = self._merge_registration(existing, acc)
                self._entries[acc.phone] = entry
                entries.append(entry)
        logger.info("Registry: registered %d accounts.", len(accounts))
        for entry in entries:
            self._persist(entry)

    async def update_state(self, phone: str, state: AccountState) -> None:
        """
        Update the AccountState for a registered phone number.

        No-op if the phone is not in the registry (logs a warning).
        """
        phone = normalize_account_phone(phone)
        async with self._lock:
            entry = self._entries.get(phone)
            if entry is None:
                logger.warning("Registry: update_state called for unknown phone %s", phone)
                return
            updated = replace(
                entry,
                state=state,
                last_checked=datetime.now(timezone.utc),
            )
            self._entries[phone] = updated
        self._persist(updated)

    async def update_proxy_state(self, phone: str, proxy_state: ProxyState) -> None:
        """Update the ProxyState for a registered phone number."""
        phone = normalize_account_phone(phone)
        async with self._lock:
            entry = self._entries.get(phone)
            if entry is None:
                logger.warning("Registry: update_proxy_state for unknown phone %s", phone)
                return
            self._entries[phone] = replace(entry, proxy_state=proxy_state)

    async def assign_role(self, phone: str, role: str) -> None:
        """Assign an organizational role tag to a registered account. Durable."""
        phone = normalize_account_phone(phone)
        async with self._lock:
            entry = self._entries.get(phone)
            if entry is None:
                logger.warning("Registry: assign_role for unknown phone %s", phone)
                return
            updated = replace(entry, role=role)
            self._entries[phone] = updated
        self._persist(updated)

    async def assign_folder(self, phone: str, folder: str) -> None:
        """Assign an organizational folder tag to a registered account. Durable."""
        phone = normalize_account_phone(phone)
        async with self._lock:
            entry = self._entries.get(phone)
            if entry is None:
                logger.warning("Registry: assign_folder for unknown phone %s", phone)
                return
            updated = replace(entry, folder=folder)
            self._entries[phone] = updated
        self._persist(updated)

    async def remove(self, phone: str) -> None:
        """Remove an account from the registry."""
        phone = normalize_account_phone(phone)
        async with self._lock:
            self._entries.pop(phone, None)

    # ------------------------------------------------------------------
    # Read operations (lock-free snapshot)
    # ------------------------------------------------------------------

    def snapshot(self) -> List[RegistryEntry]:
        """
        Return an atomic copy of all registry entries.

        The dict-copy is protected by the CPython GIL from torn reads.
        Consumers receive a stable list that won't change mid-iteration
        even if another coroutine calls update_state() concurrently.
        """
        return list(self._entries.values())

    def get(self, phone: str) -> Optional[RegistryEntry]:
        """Return the current entry for a phone, or None."""
        return self._entries.get(normalize_account_phone(phone))

    def __len__(self) -> int:
        return len(self._entries)

    def query(self) -> "AccountQuery":
        """Return a new AccountQuery over the current registry snapshot."""
        return AccountQuery(self.snapshot())


# ---------------------------------------------------------------------------
# AccountQuery — Fluent specification chain
# ---------------------------------------------------------------------------

class AccountQuery:
    """
    Immutable-style fluent query builder over a list of RegistryEntry.

    Each filter / sort method returns self, enabling method chaining.
    Filters are applied in-place to an internal list;  call execute()
    to obtain the final result.

    Design notes:
      - Entries with state=None are excluded by all status / premium filters
        (they haven't been checked yet).
      - Entries with proxy_state=None are excluded by filter_proxy_active().
      - sort_by("restriction_expires") places None values last in ascending
        order (earliest expiry first).
    """

    def __init__(self, entries: List[RegistryEntry]) -> None:
        self._entries: List[RegistryEntry] = list(entries)

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def filter_by_status(self, *statuses: AccountStatus) -> "AccountQuery":
        """Keep only entries whose state.status is in `statuses`."""
        status_set = set(statuses)
        self._entries = [
            e for e in self._entries
            if e.state is not None and e.state.status in status_set
        ]
        return self

    def filter_by_premium(self, premium: bool) -> "AccountQuery":
        """Keep only entries where state.is_premium == premium."""
        self._entries = [
            e for e in self._entries
            if e.state is not None and e.state.is_premium == premium
        ]
        return self

    def filter_proxy_active(self, active: bool = True) -> "AccountQuery":
        """Keep only entries where proxy_state.is_active == active."""
        self._entries = [
            e for e in self._entries
            if e.proxy_state is not None and e.proxy_state.is_active == active
        ]
        return self

    def filter_restriction_expiring_within(self, *, hours: float = 24.0) -> "AccountQuery":
        """
        Keep entries that have a restriction_expires set AND the expiry
        falls within the next `hours` hours from now.

        Useful for: "show accounts that will be unrestricted soon".
        """
        cutoff = datetime.now(timezone.utc) + timedelta(hours=hours)
        self._entries = [
            e for e in self._entries
            if (
                e.state is not None
                and e.state.restriction_expires is not None
                and e.state.restriction_expires <= cutoff
            )
        ]
        return self

    def filter_by_role(self, *roles: str) -> "AccountQuery":
        """Keep only entries whose role is in `roles` (exact match)."""
        role_set = set(roles)
        self._entries = [e for e in self._entries if e.role in role_set]
        return self

    def filter_by_folder(self, *folders: str) -> "AccountQuery":
        """Keep only entries whose folder is in `folders` (exact match)."""
        folder_set = set(folders)
        self._entries = [e for e in self._entries if e.folder in folder_set]
        return self

    def filter_by_country(self, *countries: str) -> "AccountQuery":
        """Keep only entries whose state.country is in `countries` (ISO region codes)."""
        country_set = set(countries)
        self._entries = [
            e for e in self._entries
            if e.state is not None and e.state.country in country_set
        ]
        return self

    def filter_by_2fa(self, has_2fa: bool) -> "AccountQuery":
        """Keep only entries where state.has_2fa == has_2fa."""
        self._entries = [
            e for e in self._entries
            if e.state is not None and e.state.has_2fa == has_2fa
        ]
        return self

    def filter_by_age_days(
        self, *, min_days: Optional[float] = None, max_days: Optional[float] = None
    ) -> "AccountQuery":
        """
        Keep entries whose age (now - first_seen, "отлежка") falls within
        [min_days, max_days] (either bound optional). Entries with no
        first_seen are excluded — age is unknown, not zero.
        """
        now = datetime.now(timezone.utc)

        def _age_days(e: RegistryEntry) -> Optional[float]:
            if e.first_seen is None:
                return None
            return (now - e.first_seen).total_seconds() / 86400.0

        def _in_range(e: RegistryEntry) -> bool:
            age = _age_days(e)
            if age is None:
                return False
            if min_days is not None and age < min_days:
                return False
            if max_days is not None and age > max_days:
                return False
            return True

        self._entries = [e for e in self._entries if _in_range(e)]
        return self

    def search(self, mask: str) -> "AccountQuery":
        """
        Keep entries where `mask` appears (case-insensitive substring match)
        in any of: phone, username, first_name.
        """
        lower = mask.lower()

        def _matches(e: RegistryEntry) -> bool:
            if lower in e.account.phone.lower():
                return True
            if e.state is None:
                return False
            if e.state.username and lower in e.state.username.lower():
                return True
            if e.state.first_name and lower in e.state.first_name.lower():
                return True
            return False

        self._entries = [e for e in self._entries if _matches(e)]
        return self

    def search_by_phone(self, mask: str) -> "AccountQuery":
        """Substring match on phone only."""
        lower = mask.lower()
        self._entries = [e for e in self._entries if lower in e.account.phone.lower()]
        return self

    def search_by_username(self, mask: str) -> "AccountQuery":
        """Substring match on state.username only."""
        lower = mask.lower()
        self._entries = [
            e for e in self._entries
            if e.state is not None
            and e.state.username
            and lower in e.state.username.lower()
        ]
        return self

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------

    def sort_by(
        self,
        field: str,
        *,
        reverse: bool = False,
    ) -> "AccountQuery":
        """
        Sort entries by a named field.

        Supported fields:
          "username"             — alphabetically by state.username
          "status"               — alphabetically by status value
          "restriction_expires"  — chronologically; None → sorted last
          "latency_ms"           — by proxy_state.latency_ms; None → sorted last
          "phone"                — by account.phone
          "last_checked"         — by last_checked timestamp; None → sorted last
          "country"              — by state.country (ISO region code); None → sorted last
          "role"                 — alphabetically by role
          "folder"               — alphabetically by folder
          "first_seen"           — chronologically ("отлежка"); None → sorted last

        None values are always placed at the END regardless of `reverse`.
        """
        _SENTINELS = {
            "restriction_expires": datetime.max.replace(tzinfo=timezone.utc),
            "latency_ms": float("inf"),
            "last_checked": datetime.max.replace(tzinfo=timezone.utc),
            "country": "￿",
            "first_seen": datetime.max.replace(tzinfo=timezone.utc),
        }

        def _key(e: RegistryEntry):
            if field == "username":
                return (e.state.username if e.state else "") or ""
            if field == "status":
                return (e.state.status.value if e.state else "")
            if field == "phone":
                return e.account.phone
            if field == "restriction_expires":
                expires = e.state.restriction_expires if e.state else None
                return expires if expires is not None else _SENTINELS["restriction_expires"]
            if field == "latency_ms":
                latency = e.proxy_state.latency_ms if e.proxy_state else None
                return latency if latency is not None else _SENTINELS["latency_ms"]
            if field == "last_checked":
                ts = e.last_checked
                return ts if ts is not None else _SENTINELS["last_checked"]
            if field == "country":
                country = e.state.country if e.state else None
                return country if country is not None else _SENTINELS["country"]
            if field == "role":
                return e.role
            if field == "folder":
                return e.folder
            if field == "first_seen":
                return e.first_seen if e.first_seen is not None else _SENTINELS["first_seen"]
            raise ValueError(f"AccountQuery.sort_by: unknown field {field!r}")

        # None-valued entries always go last regardless of reverse direction.
        # Separate them out, sort only the non-None bucket, then append.
        _sentinel_values = set(_SENTINELS.values())
        nones = [e for e in self._entries if _key(e) in _sentinel_values]
        valued = [e for e in self._entries if _key(e) not in _sentinel_values]
        valued.sort(key=_key, reverse=reverse)
        self._entries = valued + nones
        return self

    # ------------------------------------------------------------------
    # Terminal operations
    # ------------------------------------------------------------------

    def execute(self) -> List[RegistryEntry]:
        """Return the filtered and sorted list of RegistryEntry objects."""
        return list(self._entries)

    def count(self) -> int:
        """Return the number of entries matching current filters."""
        return len(self._entries)

    def first(self) -> Optional[RegistryEntry]:
        """Return the first matching entry, or None if the result set is empty."""
        return self._entries[0] if self._entries else None
