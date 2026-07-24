"""
tests/test_account_registry.py — Tests for src/account_registry.py,
proxy_checker latency/timeout, and health_checker date parsing.

Scenarios:

  AccountRegistry:
    1.  register() adds entry; snapshot() returns it.
    2.  register_many() bulk-registers; len() correct.
    3.  update_state() populates state on existing entry.
    4.  update_state() on unknown phone is a no-op (no exception).
    5.  update_proxy_state() populates proxy_state.
    6.  remove() removes an entry; snapshot returns empty.
    7.  get() returns correct entry or None.

  AccountQuery — filter pipeline:
    8.  filter_by_status(ALIVE) keeps only alive entries.
    9.  filter_by_status(ALIVE, SPAMBLOCK) keeps both statuses.
    10. filter_by_premium(True) keeps only premium accounts.
    11. filter_by_premium(True) + filter_by_status(ALIVE) → intersection.
    12. filter_proxy_active(True) keeps only entries with active proxy.
    13. filter_proxy_active(False) keeps only dead-proxy entries.
    14. Full pipeline: alive + premium + active proxy → correct intersection.
    15. filter_restriction_expiring_within(hours=24) keeps entries expiring soon.
    16. filter_restriction_expiring_within excludes entries expiring in 48h.
    17. search() finds by phone substring.
    18. search() finds by username substring (case-insensitive).
    19. search() finds by first_name substring.
    20. search_by_username() only matches username field.
    21. count() returns correct number.
    22. first() returns first entry or None.
    23. execute() on empty result returns [].

  AccountQuery — sorting:
    24. sort_by("phone") — alphabetical.
    25. sort_by("restriction_expires") ascending — earliest first, None last.
    26. sort_by("restriction_expires") descending — latest first, None still last.
    27. sort_by("latency_ms") — smallest first, None last.
    28. sort_by("status") — alphabetical by status value.
    29. Mixed None/non-None restriction_expires: None always at end.

  Health checker — restriction date parsing:
    30. "until January 15, 2024" → datetime(2024, 1, 15).
    31. "until 15 January 2024" → datetime(2024, 1, 15).
    32. "до 15 января 2024" → datetime(2024, 1, 15).
    33. "until 2024-01-15" → datetime(2024, 1, 15).
    34. "до 15.01.2024" → datetime(2024, 1, 15).
    35. Text without date → None.
    36. SpamBot mock with date → HealthResult.restriction_expires set.
    37. SpamBot mock without date → restriction_expires is None.

  Proxy checker:
    38. Successful connection → ProxyState(is_active=True, latency_ms>0).
    39. Timeout → ProxyState(is_active=False, error_message contains "Timed out").
    40. Connection refused → ProxyState(is_active=False).
    41. Unknown proxy type → ProxyState(is_active=False, error_message set).
    42. Missing host → ProxyState(is_active=False, error_message set).
    43. SOCKS5 auth failure → ProxyState(is_active=False).
    44. check_proxy never raises — always returns ProxyState.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.accounts.account_registry import AccountQuery, AccountRegistry, RegistryEntry
from src.config import AccountConfig, ProxyConfig
from src.accounts.health_checker import (
    AccountState,
    AccountStatus,
    HealthChecker,
    HealthResult,
    _parse_restriction_date,
)
from src.proxy.proxy_checker import (
    ProxyState,
    ProxyType,
    check_account_proxies,
    check_all_proxies,
    check_proxy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_account(phone: str = "+79001234567") -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone)


def make_state(
    status: AccountStatus = AccountStatus.ALIVE,
    premium: bool = False,
    expires: datetime | None = None,
    username: str = "",
    first_name: str = "",
    country: str | None = None,
    has_2fa: bool = False,
) -> AccountState:
    return AccountState(
        status=status,
        is_premium=premium,
        restriction_expires=expires,
        username=username,
        first_name=first_name,
        country=country,
        has_2fa=has_2fa,
    )


def make_proxy(
    active: bool = True,
    latency: float = 50.0,
    proxy_type: ProxyType = ProxyType.SOCKS5,
) -> ProxyState:
    return ProxyState(
        is_active=active,
        latency_ms=latency,
        proxy_type=proxy_type,
        error_message=None if active else "Connection refused",
    )


def make_entry(
    phone: str = "+79001234567",
    status: AccountStatus = AccountStatus.ALIVE,
    premium: bool = False,
    expires: datetime | None = None,
    proxy_active: bool | None = True,
    latency: float = 50.0,
    username: str = "",
    first_name: str = "",
    country: str | None = None,
    has_2fa: bool = False,
    role: str = "",
    folder: str = "",
    first_seen: datetime | None = None,
) -> RegistryEntry:
    state = make_state(status, premium, expires, username, first_name, country, has_2fa)
    proxy = make_proxy(proxy_active, latency) if proxy_active is not None else None
    return RegistryEntry(
        account=make_account(phone),
        state=state,
        proxy_state=proxy,
        role=role,
        folder=folder,
        first_seen=first_seen,
    )


_NOW = datetime.now(timezone.utc)
_IN_12H = _NOW + timedelta(hours=12)
_IN_48H = _NOW + timedelta(hours=48)
_IN_7D  = _NOW + timedelta(days=7)


# ---------------------------------------------------------------------------
# AccountRegistry
# ---------------------------------------------------------------------------

class TestAccountRegistry:
    async def test_close_without_repository_is_idempotent(self):
        reg = AccountRegistry()

        await reg.close()
        await reg.close()

    async def test_close_drains_repository_writes_in_submission_order(self):
        repository = MagicMock()
        persisted = []

        async def upsert(entry):
            persisted.append((entry.account.phone, entry.role))

        repository.upsert = AsyncMock(side_effect=upsert)
        reg = AccountRegistry(repository=repository)

        await reg.register(make_account("+7001"))
        await reg.assign_role("+7001", "sender")
        await reg.close()

        assert persisted == [("+7001", ""), ("+7001", "sender")]

    async def test_register_and_snapshot(self):
        reg = AccountRegistry()
        acc = make_account("+7001")
        await reg.register(acc)
        snap = reg.snapshot()
        assert len(snap) == 1
        assert snap[0].account.phone == "+7001"

    async def test_register_many(self):
        reg = AccountRegistry()
        accounts = [make_account(f"+700{i}") for i in range(5)]
        await reg.register_many(accounts)
        assert len(reg) == 5

    async def test_register_many_deduplicates_phone_with_and_without_plus(self):
        reg = AccountRegistry()

        await reg.register_many([make_account("+918295123844"), make_account("918295123844")])

        assert len(reg) == 1
        assert reg.snapshot()[0].account.phone == "+918295123844"

    async def test_register_sets_first_seen(self):
        reg = AccountRegistry()
        await reg.register(make_account("+7001"))
        assert reg.get("+7001").first_seen is not None

    async def test_re_register_preserves_first_seen(self):
        reg = AccountRegistry()
        acc = make_account("+7001")
        await reg.register(acc)
        original_first_seen = reg.get("+7001").first_seen

        await reg.register(acc)  # simulates a second health-check pass

        assert reg.get("+7001").first_seen == original_first_seen

    async def test_register_many_preserves_first_seen_for_known_phones(self):
        reg = AccountRegistry()
        acc = make_account("+7001")
        await reg.register(acc)
        original_first_seen = reg.get("+7001").first_seen

        await reg.register_many([acc, make_account("+7002")])

        assert reg.get("+7001").first_seen == original_first_seen
        assert reg.get("+7002").first_seen is not None

    async def test_re_register_preserves_role_folder_and_state(self):
        """register()/register_many() must not wipe role/folder/state on a known phone.

        Regression: main.py re-registers the whole pool on every health-check run
        (register_many), which previously reset role/folder/state to defaults and
        persisted the wipe to the durable store.
        """
        reg = AccountRegistry()
        acc = make_account("+7001")
        await reg.register(acc)
        await reg.assign_role("+7001", "sender")
        await reg.assign_folder("+7001", "batch-1")
        await reg.update_state("+7001", make_state(AccountStatus.SPAMBLOCK, premium=True))

        await reg.register(acc)  # simulates a second health-check pass

        entry = reg.get("+7001")
        assert entry.role == "sender"
        assert entry.folder == "batch-1"
        assert entry.state is not None
        assert entry.state.status == AccountStatus.SPAMBLOCK

    async def test_register_many_preserves_role_folder_and_state(self):
        reg = AccountRegistry()
        acc1, acc2 = make_account("+7001"), make_account("+7002")
        await reg.register_many([acc1, acc2])
        await reg.assign_role("+7001", "sender")
        await reg.update_state("+7002", make_state(AccountStatus.BANNED))

        await reg.register_many([acc1, acc2])  # e.g. main.py's startup health-check pass

        assert reg.get("+7001").role == "sender"
        assert reg.get("+7002").state.status == AccountStatus.BANNED

    async def test_update_state_preserves_first_seen(self):
        reg = AccountRegistry()
        await reg.register(make_account("+7001"))
        original_first_seen = reg.get("+7001").first_seen

        await reg.update_state("+7001", make_state(AccountStatus.ALIVE))

        assert reg.get("+7001").first_seen == original_first_seen

    async def test_update_state(self):
        reg = AccountRegistry()
        await reg.register(make_account("+7001"))
        state = make_state(AccountStatus.SPAMBLOCK, premium=True)
        await reg.update_state("+7001", state)
        entry = reg.get("+7001")
        assert entry is not None
        assert entry.state.status == AccountStatus.SPAMBLOCK
        assert entry.state.is_premium is True

    async def test_update_state_accepts_phone_without_plus(self):
        reg = AccountRegistry()
        await reg.register(make_account("+7001"))

        await reg.update_state("7001", make_state(AccountStatus.ALIVE))

        assert reg.get("+7001").state.status == AccountStatus.ALIVE
        assert reg.get("7001").state.status == AccountStatus.ALIVE

    async def test_update_state_unknown_phone_noop(self):
        reg = AccountRegistry()
        # Should not raise
        await reg.update_state("+7999", make_state())

    async def test_update_proxy_state(self):
        reg = AccountRegistry()
        await reg.register(make_account("+7001"))
        ps = make_proxy(active=False, latency=0.0)
        await reg.update_proxy_state("+7001", ps)
        entry = reg.get("+7001")
        assert entry.proxy_state.is_active is False

    async def test_assign_role(self):
        reg = AccountRegistry()
        await reg.register(make_account("+7001"))
        await reg.assign_role("+7001", "sender")
        assert reg.get("+7001").role == "sender"

    async def test_assign_role_accepts_phone_without_plus(self):
        reg = AccountRegistry()
        await reg.register(make_account("+7001"))

        await reg.assign_role("7001", "sender")

        assert reg.get("+7001").role == "sender"

    async def test_assign_role_unknown_phone_noop(self):
        reg = AccountRegistry()
        await reg.assign_role("+7999", "sender")  # should not raise

    async def test_assign_folder(self):
        reg = AccountRegistry()
        await reg.register(make_account("+7001"))
        await reg.assign_folder("+7001", "batch-1")
        assert reg.get("+7001").folder == "batch-1"

    async def test_assign_folder_unknown_phone_noop(self):
        reg = AccountRegistry()
        await reg.assign_folder("+7999", "batch-1")  # should not raise

    async def test_assign_role_preserves_other_fields(self):
        reg = AccountRegistry()
        await reg.register(make_account("+7001"))
        await reg.update_state("+7001", make_state(AccountStatus.ALIVE, premium=True))
        await reg.assign_role("+7001", "sender")
        entry = reg.get("+7001")
        assert entry.role == "sender"
        assert entry.state.is_premium is True

    async def test_remove(self):
        reg = AccountRegistry()
        await reg.register(make_account("+7001"))
        await reg.remove("+7001")
        assert len(reg.snapshot()) == 0

    async def test_get_returns_none_for_missing(self):
        reg = AccountRegistry()
        assert reg.get("+7999") is None


# ---------------------------------------------------------------------------
# AccountQuery — filters
# ---------------------------------------------------------------------------

class TestAccountQueryFilters:
    def _make_entries(self) -> list[RegistryEntry]:
        return [
            make_entry("+7001", AccountStatus.ALIVE,     premium=True,  proxy_active=True,  latency=30.0, username="alice"),
            make_entry("+7002", AccountStatus.ALIVE,     premium=False, proxy_active=True,  latency=80.0, username="bob"),
            make_entry("+7003", AccountStatus.SPAMBLOCK, premium=True,  proxy_active=True,  latency=50.0, expires=_IN_12H),
            make_entry("+7004", AccountStatus.BANNED,    premium=False, proxy_active=False, latency=0.0,  username="carol"),
            make_entry("+7005", AccountStatus.ALIVE,     premium=True,  proxy_active=True,  latency=20.0, first_name="Иван"),
        ]

    def test_filter_by_status_single(self):
        result = AccountQuery(self._make_entries()).filter_by_status(AccountStatus.ALIVE).execute()
        assert len(result) == 3
        assert all(e.state.status == AccountStatus.ALIVE for e in result)

    def test_filter_by_status_multiple(self):
        result = (
            AccountQuery(self._make_entries())
            .filter_by_status(AccountStatus.ALIVE, AccountStatus.SPAMBLOCK)
            .execute()
        )
        assert len(result) == 4

    def test_filter_by_premium_true(self):
        result = AccountQuery(self._make_entries()).filter_by_premium(True).execute()
        assert len(result) == 3
        assert all(e.state.is_premium for e in result)

    def test_filter_alive_and_premium_intersection(self):
        result = (
            AccountQuery(self._make_entries())
            .filter_by_status(AccountStatus.ALIVE)
            .filter_by_premium(True)
            .execute()
        )
        assert len(result) == 2
        phones = {e.account.phone for e in result}
        assert "+7001" in phones
        assert "+7005" in phones

    def test_filter_proxy_active_true(self):
        result = AccountQuery(self._make_entries()).filter_proxy_active(True).execute()
        assert len(result) == 4

    def test_filter_proxy_active_false(self):
        result = AccountQuery(self._make_entries()).filter_proxy_active(False).execute()
        assert len(result) == 1
        assert result[0].account.phone == "+7004"

    def test_full_pipeline_alive_premium_proxy(self):
        """Intersection: alive + premium + active proxy."""
        result = (
            AccountQuery(self._make_entries())
            .filter_by_status(AccountStatus.ALIVE)
            .filter_by_premium(True)
            .filter_proxy_active(True)
            .execute()
        )
        phones = {e.account.phone for e in result}
        assert phones == {"+7001", "+7005"}

    def test_filter_restriction_expiring_within_24h(self):
        entries = [
            make_entry("+7001", AccountStatus.SPAMBLOCK, expires=_IN_12H),
            make_entry("+7002", AccountStatus.SPAMBLOCK, expires=_IN_48H),
            make_entry("+7003", AccountStatus.SPAMBLOCK, expires=None),
        ]
        result = (
            AccountQuery(entries)
            .filter_restriction_expiring_within(hours=24)
            .execute()
        )
        assert len(result) == 1
        assert result[0].account.phone == "+7001"

    def test_filter_restriction_expiring_excludes_distant(self):
        entries = [make_entry("+7001", AccountStatus.SPAMBLOCK, expires=_IN_7D)]
        result = AccountQuery(entries).filter_restriction_expiring_within(hours=24).execute()
        assert len(result) == 0

    def test_search_by_phone(self):
        result = AccountQuery(self._make_entries()).search("+7001").execute()
        assert len(result) == 1
        assert result[0].account.phone == "+7001"

    def test_search_by_username_case_insensitive(self):
        result = AccountQuery(self._make_entries()).search("ALICE").execute()
        assert len(result) == 1
        assert result[0].state.username == "alice"

    def test_search_by_first_name(self):
        result = AccountQuery(self._make_entries()).search("Иван").execute()
        assert len(result) == 1
        assert result[0].account.phone == "+7005"

    def test_search_by_username_only(self):
        result = AccountQuery(self._make_entries()).search_by_username("bob").execute()
        assert len(result) == 1
        assert result[0].state.username == "bob"

    def test_count(self):
        count = AccountQuery(self._make_entries()).filter_by_status(AccountStatus.ALIVE).count()
        assert count == 3

    def test_first_returns_entry(self):
        entry = AccountQuery(self._make_entries()).filter_by_status(AccountStatus.ALIVE).first()
        assert entry is not None
        assert entry.state.status == AccountStatus.ALIVE

    def test_first_returns_none_on_empty(self):
        entry = AccountQuery([]).first()
        assert entry is None

    def test_execute_on_empty_result(self):
        result = AccountQuery(self._make_entries()).filter_by_status(AccountStatus.UNKNOWN).execute()
        assert result == []


# ---------------------------------------------------------------------------
# AccountQuery — geo / 2FA / role / folder / age filters
# ---------------------------------------------------------------------------

class TestAccountQueryOrganizationFilters:
    def _make_entries(self) -> list[RegistryEntry]:
        now = datetime.now(timezone.utc)
        return [
            make_entry("+7001", country="RU", has_2fa=True, role="sender", folder="batch-1",
                       first_seen=now - timedelta(days=10)),
            make_entry("+7002", country="US", has_2fa=False, role="scraper", folder="batch-1",
                       first_seen=now - timedelta(days=1)),
            make_entry("+7003", country="RU", has_2fa=False, role="sender", folder="batch-2",
                       first_seen=None),
        ]

    def test_filter_by_role(self):
        result = AccountQuery(self._make_entries()).filter_by_role("sender").execute()
        assert {e.account.phone for e in result} == {"+7001", "+7003"}

    def test_filter_by_folder(self):
        result = AccountQuery(self._make_entries()).filter_by_folder("batch-1").execute()
        assert {e.account.phone for e in result} == {"+7001", "+7002"}

    def test_filter_by_multiple_folders(self):
        result = AccountQuery(self._make_entries()).filter_by_folder("batch-1", "batch-2").execute()
        assert len(result) == 3

    def test_filter_by_country(self):
        result = AccountQuery(self._make_entries()).filter_by_country("RU").execute()
        assert {e.account.phone for e in result} == {"+7001", "+7003"}

    def test_filter_by_country_excludes_unknown(self):
        entries = self._make_entries() + [make_entry("+7004", country=None)]
        result = AccountQuery(entries).filter_by_country("RU").execute()
        assert all(e.account.phone != "+7004" for e in result)

    def test_filter_by_2fa_true(self):
        result = AccountQuery(self._make_entries()).filter_by_2fa(True).execute()
        assert {e.account.phone for e in result} == {"+7001"}

    def test_filter_by_2fa_false(self):
        result = AccountQuery(self._make_entries()).filter_by_2fa(False).execute()
        assert {e.account.phone for e in result} == {"+7002", "+7003"}

    def test_filter_by_age_days_min(self):
        result = AccountQuery(self._make_entries()).filter_by_age_days(min_days=5).execute()
        assert {e.account.phone for e in result} == {"+7001"}

    def test_filter_by_age_days_max(self):
        result = AccountQuery(self._make_entries()).filter_by_age_days(max_days=5).execute()
        assert {e.account.phone for e in result} == {"+7002"}

    def test_filter_by_age_days_excludes_unknown_first_seen(self):
        result = AccountQuery(self._make_entries()).filter_by_age_days(min_days=0).execute()
        assert all(e.account.phone != "+7003" for e in result)

    def test_filter_by_age_days_range(self):
        result = (
            AccountQuery(self._make_entries())
            .filter_by_age_days(min_days=0, max_days=20)
            .execute()
        )
        assert {e.account.phone for e in result} == {"+7001", "+7002"}


# ---------------------------------------------------------------------------
# AccountQuery — sorting
# ---------------------------------------------------------------------------

class TestAccountQuerySorting:
    def test_sort_by_phone(self):
        entries = [
            make_entry("+7003"),
            make_entry("+7001"),
            make_entry("+7002"),
        ]
        result = AccountQuery(entries).sort_by("phone").execute()
        phones = [e.account.phone for e in result]
        assert phones == sorted(phones)

    def test_sort_by_restriction_expires_ascending(self):
        """Earliest expiry first; None always at end."""
        entries = [
            make_entry("+7001", AccountStatus.SPAMBLOCK, expires=_IN_48H),
            make_entry("+7002", AccountStatus.SPAMBLOCK, expires=None),
            make_entry("+7003", AccountStatus.SPAMBLOCK, expires=_IN_12H),
        ]
        result = AccountQuery(entries).sort_by("restriction_expires").execute()
        phones = [e.account.phone for e in result]
        assert phones == ["+7003", "+7001", "+7002"]  # None (+7002) last

    def test_sort_by_restriction_expires_descending_none_still_last(self):
        """Descending (latest first); None still at end."""
        entries = [
            make_entry("+7001", AccountStatus.SPAMBLOCK, expires=_IN_12H),
            make_entry("+7002", AccountStatus.SPAMBLOCK, expires=None),
            make_entry("+7003", AccountStatus.SPAMBLOCK, expires=_IN_48H),
        ]
        result = AccountQuery(entries).sort_by("restriction_expires", reverse=True).execute()
        phones = [e.account.phone for e in result]
        # +7003 (48h) > +7001 (12h) > +7002 (None)
        assert phones == ["+7003", "+7001", "+7002"]

    def test_sort_by_latency_ms(self):
        entries = [
            make_entry("+7001", latency=100.0),
            make_entry("+7002", latency=20.0),
            make_entry("+7003", latency=50.0),
        ]
        result = AccountQuery(entries).sort_by("latency_ms").execute()
        latencies = [e.proxy_state.latency_ms for e in result]
        assert latencies == [20.0, 50.0, 100.0]

    def test_sort_by_status_alphabetical(self):
        entries = [
            make_entry("+7001", AccountStatus.SPAMBLOCK),
            make_entry("+7002", AccountStatus.ALIVE),
            make_entry("+7003", AccountStatus.BANNED),
        ]
        result = AccountQuery(entries).sort_by("status").execute()
        statuses = [e.state.status.value for e in result]
        assert statuses == sorted(statuses)

    def test_none_expires_always_at_end_regardless_of_order(self):
        """None must be last in BOTH ascending and descending sorts."""
        entries = [
            make_entry("+7001", AccountStatus.SPAMBLOCK, expires=_IN_12H),
            make_entry("+7002", AccountStatus.SPAMBLOCK, expires=None),
        ]
        asc = AccountQuery(entries).sort_by("restriction_expires").execute()
        desc = AccountQuery(entries).sort_by("restriction_expires", reverse=True).execute()
        assert asc[-1].account.phone == "+7002"
        assert desc[-1].account.phone == "+7002"

    def test_unknown_sort_field_raises(self):
        with pytest.raises(ValueError, match="unknown field"):
            AccountQuery([make_entry()]).sort_by("nonexistent").execute()

    def test_sort_by_country_none_last(self):
        entries = [
            make_entry("+7001", country="US"),
            make_entry("+7002", country=None),
            make_entry("+7003", country="RU"),
        ]
        result = AccountQuery(entries).sort_by("country").execute()
        phones = [e.account.phone for e in result]
        assert phones == ["+7003", "+7001", "+7002"]  # RU, US, then None last

    def test_sort_by_role_alphabetical(self):
        entries = [
            make_entry("+7001", role="scraper"),
            make_entry("+7002", role="sender"),
            make_entry("+7003", role="backup"),
        ]
        result = AccountQuery(entries).sort_by("role").execute()
        roles = [e.role for e in result]
        assert roles == sorted(roles)

    def test_sort_by_folder_alphabetical(self):
        entries = [
            make_entry("+7001", folder="batch-2"),
            make_entry("+7002", folder="batch-1"),
        ]
        result = AccountQuery(entries).sort_by("folder").execute()
        assert [e.folder for e in result] == ["batch-1", "batch-2"]

    def test_sort_by_first_seen_none_last(self):
        now = datetime.now(timezone.utc)
        entries = [
            make_entry("+7001", first_seen=now - timedelta(days=1)),
            make_entry("+7002", first_seen=None),
            make_entry("+7003", first_seen=now - timedelta(days=10)),
        ]
        result = AccountQuery(entries).sort_by("first_seen").execute()
        phones = [e.account.phone for e in result]
        assert phones == ["+7003", "+7001", "+7002"]  # oldest first, None last


# ---------------------------------------------------------------------------
# Health checker — _parse_restriction_date
# ---------------------------------------------------------------------------

class TestParseRestrictionDate:
    def test_en_month_first(self):
        dt = _parse_restriction_date("Your account was restricted until January 15, 2024.")
        assert dt == datetime(2024, 1, 15, tzinfo=timezone.utc)

    def test_en_day_first(self):
        dt = _parse_restriction_date("Account limited until 15 January 2024.")
        assert dt == datetime(2024, 1, 15, tzinfo=timezone.utc)

    def test_ru_text(self):
        dt = _parse_restriction_date("Ограничение действует до 15 января 2024 года.")
        assert dt == datetime(2024, 1, 15, tzinfo=timezone.utc)

    def test_iso_format(self):
        dt = _parse_restriction_date("Account restricted until 2024-01-15.")
        assert dt == datetime(2024, 1, 15, tzinfo=timezone.utc)

    def test_ru_dot_notation(self):
        dt = _parse_restriction_date("Ограничен до 15.01.2024.")
        assert dt == datetime(2024, 1, 15, tzinfo=timezone.utc)

    def test_no_date_returns_none(self):
        dt = _parse_restriction_date("Your account is restricted due to spam complaints.")
        assert dt is None

    def test_clean_message_returns_none(self):
        dt = _parse_restriction_date("Good news, no limits are currently imposed on your account.")
        assert dt is None

    def test_result_is_utc(self):
        dt = _parse_restriction_date("until 2025-06-01")
        assert dt is not None
        assert dt.tzinfo == timezone.utc


class TestSpamBotIntegration:
    """Mock-level tests for _check_spambot date extraction."""

    def _make_mock_client(self, reply_text: str):
        client = AsyncMock()
        client.get_entity = AsyncMock(return_value=MagicMock(id=178220800))
        client.send_message = AsyncMock()
        msg = MagicMock()
        msg.text = reply_text
        msg.out = False
        client.get_messages = AsyncMock(return_value=[msg])
        return client

    async def test_spambot_with_date_sets_restriction_expires(self):
        checker = HealthChecker()
        client = self._make_mock_client(
            "Unfortunately, your account was restricted until January 15, 2024."
        )
        with (
            patch("src.accounts.health_checker.asyncio.sleep", new_callable=AsyncMock),
            patch("src.accounts.health_checker._SPAMBOT_REPLY_TIMEOUT", 30.0),
        ):
            result = await checker._check_spambot(client, "+7001")

        assert result is not None
        assert result.status == AccountStatus.SPAMBLOCK
        assert result.restriction_expires == datetime(2024, 1, 15, tzinfo=timezone.utc)

    async def test_spambot_without_date_restriction_expires_none(self):
        checker = HealthChecker()
        client = self._make_mock_client(
            "Your account is restricted because of spam reports."
        )
        with (
            patch("src.accounts.health_checker.asyncio.sleep", new_callable=AsyncMock),
            patch("src.accounts.health_checker._SPAMBOT_REPLY_TIMEOUT", 30.0),
        ):
            result = await checker._check_spambot(client, "+7001")

        assert result is not None
        assert result.status == AccountStatus.SPAMBLOCK
        assert result.restriction_expires is None

    async def test_spambot_frozen_sets_frozen_status(self):
        checker = HealthChecker()
        client = self._make_mock_client("Your account is currently frozen.")
        with (
            patch("src.accounts.health_checker.asyncio.sleep", new_callable=AsyncMock),
            patch("src.accounts.health_checker._SPAMBOT_REPLY_TIMEOUT", 30.0),
        ):
            result = await checker._check_spambot(client, "+7001")

        assert result is not None
        assert result.status == AccountStatus.FROZEN


# ---------------------------------------------------------------------------
# Proxy checker
# ---------------------------------------------------------------------------

class TestCheckProxy:
    async def test_successful_socks5_returns_active(self):
        """Mock asyncio.open_connection + SOCKS5 handshake bytes."""
        reader = AsyncMock()
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        # Simulate SOCKS5 handshake:
        # greeting (method=0x00 no-auth), then CONNECT reply (success, IPv4)
        reader.readexactly = AsyncMock(side_effect=[
            bytes([0x05, 0x00]),           # method negotiation → no-auth
            bytes([0x05, 0x00, 0x00, 0x01]),  # CONNECT reply header (REP=0x00 success, ATYP=IPv4)
            bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # bound addr (4) + port (2)
        ])

        with patch("src.proxy.proxy_checker.asyncio.open_connection", return_value=(reader, writer)):
            state = await check_proxy({
                "type": "socks5",
                "host": "proxy.example.com",
                "port": 1080,
            })

        assert state.is_active is True
        assert state.latency_ms >= 0
        assert state.proxy_type == ProxyType.SOCKS5
        assert state.error_message is None

    async def test_timeout_returns_inactive_with_message(self):
        with patch(
            "src.proxy.proxy_checker.asyncio.open_connection",
            side_effect=asyncio.TimeoutError(),
        ):
            state = await check_proxy({
                "type": "socks5",
                "host": "dead.proxy.example.com",
                "port": 1080,
                "timeout": 0.001,
            }, retries=0)

        assert state.is_active is False
        assert "Timed out" in (state.error_message or "")
        assert state.proxy_type == ProxyType.SOCKS5

    async def test_connection_refused_returns_inactive(self):
        with patch(
            "src.proxy.proxy_checker.asyncio.open_connection",
            side_effect=ConnectionRefusedError("Connection refused"),
        ):
            state = await check_proxy({
                "type": "socks5",
                "host": "127.0.0.1",
                "port": 9999,
            }, retries=0)

        assert state.is_active is False
        assert state.error_message is not None

    async def test_unknown_proxy_type_returns_inactive(self):
        state = await check_proxy({"type": "ftp", "host": "h", "port": 21})
        assert state.is_active is False
        assert "Unknown proxy type" in (state.error_message or "")

    async def test_missing_host_returns_inactive(self):
        state = await check_proxy({"type": "socks5", "host": "", "port": 0})
        assert state.is_active is False
        assert state.error_message is not None

    async def test_socks5_auth_failure_returns_inactive(self):
        reader = AsyncMock()
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        # Server accepts user/pass auth method, then rejects credentials
        reader.readexactly = AsyncMock(side_effect=[
            bytes([0x05, 0x02]),   # method 0x02 = user/pass
            bytes([0x01, 0xFF]),   # auth response: VER=1, STATUS=0xFF (fail)
        ])

        with patch("src.proxy.proxy_checker.asyncio.open_connection", return_value=(reader, writer)):
            # retries=0: this test's mock is single-shot (a finite side_effect
            # list for readexactly), it isn't exercising retry behavior.
            state = await check_proxy({
                "type": "socks5",
                "host": "proxy.example.com",
                "port": 1080,
                "username": "user",
                "password": "wrongpass",
            }, retries=0)

        assert state.is_active is False
        assert "authentication failed" in (state.error_message or "").lower()

    async def test_check_proxy_never_raises(self):
        """check_proxy must always return ProxyState, never raise."""
        with patch(
            "src.proxy.proxy_checker.asyncio.open_connection",
            side_effect=RuntimeError("unexpected error"),
        ):
            state = await check_proxy({"type": "socks5", "host": "h", "port": 1080}, retries=0)

        assert isinstance(state, ProxyState)
        assert state.is_active is False

    async def test_http_proxy_success(self):
        reader = AsyncMock()
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        # HTTP CONNECT response
        reader.read = AsyncMock(
            return_value=b"HTTP/1.1 200 Connection established\r\n\r\n"
        )

        with patch("src.proxy.proxy_checker.asyncio.open_connection", return_value=(reader, writer)):
            state = await check_proxy({
                "type": "http",
                "host": "proxy.example.com",
                "port": 3128,
            })

        assert state.is_active is True
        assert state.proxy_type == ProxyType.HTTP

    async def test_http_proxy_failure_407(self):
        reader = AsyncMock()
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        reader.read = AsyncMock(
            return_value=b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n"
        )

        with patch("src.proxy.proxy_checker.asyncio.open_connection", return_value=(reader, writer)):
            state = await check_proxy({
                "type": "http",
                "host": "proxy.example.com",
                "port": 3128,
            }, retries=0)

        assert state.is_active is False
        assert "407" in (state.error_message or "")


# ---------------------------------------------------------------------------
# Proxy checker — SOCKS4 connector (previously untested)
# ---------------------------------------------------------------------------

class TestSocks4Connector:
    def _make_stream_mocks(self, response: bytes):
        reader = AsyncMock()
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        reader.readexactly = AsyncMock(return_value=response)
        return reader, writer

    def _make_mock_loop(self, ip: str = "149.154.167.50"):
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=[(2, 1, 6, "", (ip, 443))])
        return loop

    async def test_socks4_success(self):
        reader, writer = self._make_stream_mocks(
            bytes([0x00, 0x5A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])  # granted
        )
        with (
            patch("src.proxy.proxy_checker.asyncio.get_running_loop", return_value=self._make_mock_loop()),
            patch("src.proxy.proxy_checker.asyncio.open_connection", return_value=(reader, writer)),
        ):
            state = await check_proxy(
                {"type": "socks4", "host": "proxy.example.com", "port": 1080}, retries=0,
            )

        assert state.is_active is True
        assert state.proxy_type == ProxyType.SOCKS4

    async def test_socks4_rejected(self):
        reader, writer = self._make_stream_mocks(
            bytes([0x00, 0x5B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])  # rejected
        )
        with (
            patch("src.proxy.proxy_checker.asyncio.get_running_loop", return_value=self._make_mock_loop()),
            patch("src.proxy.proxy_checker.asyncio.open_connection", return_value=(reader, writer)),
        ):
            state = await check_proxy(
                {"type": "socks4", "host": "proxy.example.com", "port": 1080}, retries=0,
            )

        assert state.is_active is False
        assert "rejected" in (state.error_message or "").lower()

    async def test_socks4_dns_resolve_failure(self):
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(side_effect=OSError("dns failure"))

        with patch("src.proxy.proxy_checker.asyncio.get_running_loop", return_value=loop):
            state = await check_proxy(
                {"type": "socks4", "host": "proxy.example.com", "port": 1080}, retries=0,
            )

        assert state.is_active is False
        assert "cannot resolve" in (state.error_message or "").lower()

    async def test_socks4_dns_resolve_respects_timeout(self):
        """The resolve step must not be able to stall past the declared timeout."""
        async def _slow_getaddrinfo(*args, **kwargs):
            await asyncio.sleep(10)

        loop = MagicMock()
        loop.getaddrinfo = _slow_getaddrinfo

        with patch("src.proxy.proxy_checker.asyncio.get_running_loop", return_value=loop):
            state = await check_proxy(
                {"type": "socks4", "host": "proxy.example.com", "port": 1080, "timeout": 0.05},
                retries=0,
            )

        assert state.is_active is False
        assert "timed out" in (state.error_message or "").lower()


# ---------------------------------------------------------------------------
# Proxy checker — HTTPS (TLS) connector (previously untested)
# ---------------------------------------------------------------------------

class TestHttpsConnector:
    async def test_https_proxy_success(self):
        reader = AsyncMock()
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        reader.read = AsyncMock(return_value=b"HTTP/1.1 200 Connection established\r\n\r\n")

        with patch(
            "src.proxy.proxy_checker.asyncio.open_connection", return_value=(reader, writer)
        ) as mock_open:
            state = await check_proxy(
                {"type": "https", "host": "proxy.example.com", "port": 8443}, retries=0,
            )

        assert state.is_active is True
        assert state.proxy_type == ProxyType.HTTPS
        # ssl=True must be passed through for the HTTPS variant specifically
        assert mock_open.call_args.kwargs.get("ssl") is True


# ---------------------------------------------------------------------------
# Proxy checker — retry logic
# ---------------------------------------------------------------------------

class TestCheckProxyRetries:
    async def test_retries_until_success(self):
        call_count = 0

        async def flaky_open_connection(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionRefusedError("refused")
            reader = AsyncMock()
            writer = MagicMock()
            writer.close = MagicMock()
            writer.wait_closed = AsyncMock()
            writer.write = MagicMock()
            writer.drain = AsyncMock()
            reader.readexactly = AsyncMock(side_effect=[
                bytes([0x05, 0x00]),
                bytes([0x05, 0x00, 0x00, 0x01]),
                bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
            ])
            return reader, writer

        with patch(
            "src.proxy.proxy_checker.asyncio.open_connection", side_effect=flaky_open_connection
        ):
            state = await check_proxy(
                {"type": "socks5", "host": "h", "port": 1080}, retries=2, retry_delay=0.01,
            )

        assert state.is_active is True
        assert call_count == 3

    async def test_gives_up_after_retries_exhausted(self):
        with patch(
            "src.proxy.proxy_checker.asyncio.open_connection",
            side_effect=ConnectionRefusedError("refused"),
        ):
            state = await check_proxy(
                {"type": "socks5", "host": "h", "port": 1080}, retries=2, retry_delay=0.01,
            )

        assert state.is_active is False

    async def test_zero_retries_means_single_attempt(self):
        call_count = 0

        async def always_fail(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionRefusedError("refused")

        with patch("src.proxy.proxy_checker.asyncio.open_connection", side_effect=always_fail):
            await check_proxy(
                {"type": "socks5", "host": "h", "port": 1080}, retries=0, retry_delay=0.01,
            )

        assert call_count == 1

    async def test_config_error_is_not_retried(self):
        """An unknown proxy type is a config error -- retrying can't fix it."""
        call_count = 0

        async def track_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionRefusedError("should never be reached")

        with patch("src.proxy.proxy_checker.asyncio.open_connection", side_effect=track_calls):
            state = await check_proxy(
                {"type": "ftp", "host": "h", "port": 21}, retries=2, retry_delay=0.01,
            )

        assert state.is_active is False
        assert call_count == 0


# ---------------------------------------------------------------------------
# check_all_proxies — batch fan-out over check_proxy
# ---------------------------------------------------------------------------

class TestCheckAllProxies:
    async def test_returns_one_state_per_proxy_in_order(self):
        proxies = [
            {"host": "a", "port": 1},
            {"host": "b", "port": 2},
            {"host": "c", "port": 3},
        ]

        async def fake_check(proxy_config, **kwargs):
            return ProxyState(
                is_active=proxy_config["host"] != "b",
                latency_ms=1.0,
                proxy_type=ProxyType.SOCKS5,
            )

        with patch("src.proxy.proxy_checker.check_proxy", side_effect=fake_check):
            results = await check_all_proxies(proxies, concurrency=10)

        assert [r.is_active for r in results] == [True, False, True]

    async def test_concurrency_is_bounded(self):
        proxies = [{"host": str(i), "port": i} for i in range(6)]
        in_flight = 0
        max_in_flight = 0

        async def fake_check(proxy_config, **kwargs):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1
            return ProxyState(is_active=True, latency_ms=1.0, proxy_type=ProxyType.SOCKS5)

        with patch("src.proxy.proxy_checker.check_proxy", side_effect=fake_check):
            await check_all_proxies(proxies, concurrency=2)

        assert max_in_flight <= 2

    async def test_empty_list_returns_empty(self):
        assert await check_all_proxies([]) == []

    async def test_forwards_extra_kwargs_to_check_proxy(self):
        captured = {}

        async def fake_check(proxy_config, **kwargs):
            captured.update(kwargs)
            return ProxyState(is_active=True, latency_ms=1.0, proxy_type=ProxyType.SOCKS5)

        with patch("src.proxy.proxy_checker.check_proxy", side_effect=fake_check):
            await check_all_proxies([{"host": "a", "port": 1}], retries=0, retry_delay=0.1)

        assert captured == {"retries": 0, "retry_delay": 0.1}


# ---------------------------------------------------------------------------
# check_account_proxies — proxy preflight over AccountConfig.proxy
# ---------------------------------------------------------------------------

def _account_with_proxy(phone: str, proxy: ProxyConfig | None) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone, proxy=proxy)


class TestCheckAccountProxies:
    async def test_skips_accounts_without_proxy(self):
        accounts = [_account_with_proxy("+1", None), _account_with_proxy("+2", None)]

        result = await check_account_proxies(accounts)

        assert result == {}

    async def test_checks_only_accounts_with_proxy(self):
        proxy = ProxyConfig(host="1.2.3.4", port=1080)
        accounts = [
            _account_with_proxy("+1", proxy),
            _account_with_proxy("+2", None),
        ]

        async def fake_check(proxy_config, **kwargs):
            return ProxyState(is_active=True, latency_ms=5.0, proxy_type=ProxyType.SOCKS5)

        with patch("src.proxy.proxy_checker.check_proxy", side_effect=fake_check):
            result = await check_account_proxies(accounts)

        assert set(result.keys()) == {"+1"}
        assert result["+1"].is_active is True

    async def test_maps_proxy_config_fields_correctly(self):
        proxy = ProxyConfig(host="1.2.3.4", port=1080, username="u", password="p", proxy_type="http")
        accounts = [_account_with_proxy("+1", proxy)]
        captured = {}

        async def fake_check(proxy_config, **kwargs):
            captured.update(proxy_config)
            return ProxyState(is_active=True, latency_ms=1.0, proxy_type=ProxyType.HTTP)

        with patch("src.proxy.proxy_checker.check_proxy", side_effect=fake_check):
            await check_account_proxies(accounts)

        assert captured == {
            "type": "http", "host": "1.2.3.4", "port": 1080, "username": "u", "password": "p",
        }

    async def test_empty_account_list_returns_empty(self):
        assert await check_account_proxies([]) == {}
