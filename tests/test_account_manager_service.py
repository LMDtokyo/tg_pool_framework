"""tests/test_account_manager_service.py — AccountManagerService facade."""

import pytest

from src.accounts.account_manager_service import AccountManagerService
from src.accounts.account_registry import AccountRegistry
from src.accounts.health_checker import AccountState, AccountStatus, HealthResult, PoolHealthReport
from src.config import AccountConfig

pytestmark = pytest.mark.unit


class _FakeHealthChecker:
    def __init__(self, result_by_phone):
        self._result_by_phone = result_by_phone
        self.calls: list = []

    async def check_pool_health(self, accounts, deep_check=False, on_result=None):
        self.calls.append(([a.phone for a in accounts], deep_check))
        results = [self._result_by_phone[a.phone] for a in accounts]
        if on_result is not None:
            for result in results:
                await on_result(result)
        return PoolHealthReport(results=results)


def make_account(phone: str) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone)


def make_state(
    status: AccountStatus = AccountStatus.ALIVE,
    premium: bool = False,
    country: str = None,
    has_2fa: bool = False,
) -> AccountState:
    return AccountState(status=status, is_premium=premium, country=country, has_2fa=has_2fa)


async def _seeded_registry() -> AccountRegistry:
    reg = AccountRegistry()
    await reg.register(make_account("+70001"))
    await reg.register(make_account("+70002"))
    await reg.register(make_account("+70003"))

    await reg.update_state("+70001", make_state(AccountStatus.ALIVE, premium=True, country="RU"))
    await reg.update_state("+70002", make_state(AccountStatus.ALIVE, premium=False, country="US"))
    await reg.update_state("+70003", make_state(AccountStatus.BANNED, premium=False, country="RU"))

    await reg.assign_role("+70001", "sender")
    await reg.assign_folder("+70001", "batch-1")
    await reg.assign_role("+70002", "sender")
    await reg.assign_folder("+70002", "batch-2")

    return reg


class TestSearch:
    async def test_filter_by_status(self):
        service = AccountManagerService(await _seeded_registry(), _FakeHealthChecker({}))
        results = service.search(status=AccountStatus.ALIVE)
        assert {e.account.phone for e in results} == {"+70001", "+70002"}

    async def test_filter_by_status_accepts_sequence(self):
        service = AccountManagerService(await _seeded_registry(), _FakeHealthChecker({}))
        results = service.search(status=[AccountStatus.ALIVE, AccountStatus.BANNED])
        assert {e.account.phone for e in results} == {"+70001", "+70002", "+70003"}

    async def test_filter_by_premium(self):
        service = AccountManagerService(await _seeded_registry(), _FakeHealthChecker({}))
        results = service.search(premium=True)
        assert [e.account.phone for e in results] == ["+70001"]

    async def test_filter_by_country_single_value(self):
        service = AccountManagerService(await _seeded_registry(), _FakeHealthChecker({}))
        results = service.search(country="RU")
        assert {e.account.phone for e in results} == {"+70001", "+70003"}

    async def test_filter_by_role_and_folder(self):
        service = AccountManagerService(await _seeded_registry(), _FakeHealthChecker({}))
        results = service.search(role="sender", folder="batch-1")
        assert [e.account.phone for e in results] == ["+70001"]

    async def test_combined_filters_and_sort(self):
        service = AccountManagerService(await _seeded_registry(), _FakeHealthChecker({}))
        results = service.search(status=AccountStatus.ALIVE, role="sender", sort_by="folder", reverse=True)
        assert [e.account.phone for e in results] == ["+70002", "+70001"]

    async def test_no_filters_returns_everything(self):
        service = AccountManagerService(await _seeded_registry(), _FakeHealthChecker({}))
        results = service.search()
        assert len(results) == 3

    async def test_text_search_matches_phone(self):
        service = AccountManagerService(await _seeded_registry(), _FakeHealthChecker({}))
        results = service.search(text="70002")
        assert [e.account.phone for e in results] == ["+70002"]


class TestAssignment:
    async def test_assign_role_persists_and_is_searchable(self):
        registry = await _seeded_registry()
        service = AccountManagerService(registry, _FakeHealthChecker({}))

        await service.assign_role("+70003", "backup")

        assert registry.get("+70003").role == "backup"
        assert [e.account.phone for e in service.search(role="backup")] == ["+70003"]

    async def test_assign_folder_persists(self):
        registry = await _seeded_registry()
        service = AccountManagerService(registry, _FakeHealthChecker({}))

        await service.assign_folder("+70003", "quarantine")

        assert registry.get("+70003").folder == "quarantine"


class TestRecheck:
    async def test_recheck_whole_pool_updates_registry(self):
        registry = await _seeded_registry()
        checker = _FakeHealthChecker({
            "+70001": HealthResult(phone="+70001", status=AccountStatus.SPAMBLOCK, detail="fresh"),
            "+70002": HealthResult(phone="+70002", status=AccountStatus.ALIVE),
            "+70003": HealthResult(phone="+70003", status=AccountStatus.BANNED),
        })
        service = AccountManagerService(registry, checker)

        report = await service.recheck()

        assert len(checker.calls) == 1
        assert set(checker.calls[0][0]) == {"+70001", "+70002", "+70003"}
        assert registry.get("+70001").state.status == AccountStatus.SPAMBLOCK
        assert len(report.results) == 3

    async def test_recheck_subset_of_phones_only(self):
        registry = await _seeded_registry()
        checker = _FakeHealthChecker({
            "+70001": HealthResult(phone="+70001", status=AccountStatus.BANNED),
        })
        service = AccountManagerService(registry, checker)

        await service.recheck(["+70001"])

        assert checker.calls == [(["+70001"], False)]
        assert registry.get("+70001").state.status == AccountStatus.BANNED
        # Untouched accounts keep their prior state.
        assert registry.get("+70002").state.status == AccountStatus.ALIVE

    async def test_recheck_subset_accepts_phone_without_plus(self):
        registry = await _seeded_registry()
        checker = _FakeHealthChecker({
            "+70001": HealthResult(phone="+70001", status=AccountStatus.BANNED),
        })
        service = AccountManagerService(registry, checker)

        await service.recheck(["70001"])

        assert checker.calls == [(["+70001"], False)]
        assert registry.get("+70001").state.status == AccountStatus.BANNED

    async def test_recheck_deep_flag_forwarded(self):
        registry = await _seeded_registry()
        checker = _FakeHealthChecker({
            "+70001": HealthResult(phone="+70001", status=AccountStatus.ALIVE),
        })
        service = AccountManagerService(registry, checker)

        await service.recheck(["+70001"], deep=True)

        assert checker.calls == [(["+70001"], True)]

    async def test_recheck_empty_pool_is_a_noop(self):
        registry = AccountRegistry()
        checker = _FakeHealthChecker({})
        service = AccountManagerService(registry, checker)

        report = await service.recheck()

        assert checker.calls == [([], False)]
        assert report.results == []
