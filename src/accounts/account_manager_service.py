"""
src/accounts/account_manager_service.py — AccountManagerService facade.

Single entry point for the "account manager" surface this framework exposes
(search/filter/sort by status/premium/2FA/geo/age/role/folder, role/folder
assignment, on-demand recheck) so a future UI has one API to call instead of
reaching into AccountRegistry + AccountQuery + HealthChecker directly.

proxy_checker.check_proxy() and tdata_converter.convert_batch_tdata() are
deliberately NOT wrapped here — they're already clean, standalone, tested
functions with no shared registry state to coordinate; a future UI can call
them directly.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional, Sequence, Union

from src.accounts.account_registry import AccountRegistry, RegistryEntry
from src.accounts.health_checker import AccountStatus, HealthChecker, PoolHealthReport
from src.config import normalize_account_phone

_StrOrSeq = Union[str, Sequence[str]]


def _as_tuple(value: Optional[_StrOrSeq]) -> Optional[tuple]:
    """Normalizes a single value or a sequence of values into a tuple, or None."""
    if value is None:
        return None
    if isinstance(value, str):
        return (value,)
    return tuple(value)


class AccountManagerService:
    """
    Usage:
        service = AccountManagerService(registry, health_checker)
        alive_ru = service.search(status=AccountStatus.ALIVE, country="RU", sort_by="folder")
        await service.assign_folder("+79001234567", "batch-1")
        report = await service.recheck(deep=True)
    """

    def __init__(self, registry: AccountRegistry, health_checker: HealthChecker) -> None:
        self._registry = registry
        self._health_checker = health_checker
        self._recheck_lock = asyncio.Lock()

    def search(
        self,
        *,
        status: Optional[Union[AccountStatus, Sequence[AccountStatus]]] = None,
        premium: Optional[bool] = None,
        has_2fa: Optional[bool] = None,
        country: Optional[_StrOrSeq] = None,
        role: Optional[_StrOrSeq] = None,
        folder: Optional[_StrOrSeq] = None,
        min_age_days: Optional[float] = None,
        max_age_days: Optional[float] = None,
        text: Optional[str] = None,
        sort_by: Optional[str] = None,
        reverse: bool = False,
    ) -> List[RegistryEntry]:
        """Filter + sort the current registry snapshot. All given filters are AND-combined."""
        query = self._registry.query()

        statuses = _as_tuple(status)
        if statuses is not None:
            query = query.filter_by_status(*statuses)
        if premium is not None:
            query = query.filter_by_premium(premium)
        if has_2fa is not None:
            query = query.filter_by_2fa(has_2fa)
        countries = _as_tuple(country)
        if countries is not None:
            query = query.filter_by_country(*countries)
        roles = _as_tuple(role)
        if roles is not None:
            query = query.filter_by_role(*roles)
        folders = _as_tuple(folder)
        if folders is not None:
            query = query.filter_by_folder(*folders)
        if min_age_days is not None or max_age_days is not None:
            query = query.filter_by_age_days(min_days=min_age_days, max_days=max_age_days)
        if text:
            query = query.search(text)
        if sort_by is not None:
            query = query.sort_by(sort_by, reverse=reverse)

        return query.execute()

    async def assign_role(self, phone: str, role: str) -> None:
        await self._registry.assign_role(phone, role)

    async def assign_folder(self, phone: str, folder: str) -> None:
        await self._registry.assign_folder(phone, folder)

    async def recheck(
        self, phones: Optional[List[str]] = None, *, deep: bool = False
    ) -> PoolHealthReport:
        """
        Re-run the health check for `phones` (or the whole pool if None) and
        persist each result back into the registry.
        """
        async with self._recheck_lock:
            entries = self._registry.snapshot()
            if phones is not None:
                wanted = {normalize_account_phone(phone) for phone in phones}
                entries = [e for e in entries if e.account.phone in wanted]

            accounts = [e.account for e in entries]
            async def _store_result(result) -> None:
                await self._registry.update_state(result.phone, result.account_state)

            return await self._health_checker.check_pool_health(
                accounts,
                deep_check=deep,
                on_result=_store_result,
            )
