import pytest

from src.accounts.proxy_safety import (
    SharedProxyError,
    UnprotectedAccountsError,
    ensure_all_proxied,
    ensure_no_shared_proxies,
    shared_proxy_groups,
    unproxied_phones,
)
from src.config import AccountConfig, ProxyConfig

pytestmark = pytest.mark.unit


def _account(phone: str, proxy: ProxyConfig | None = None) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="hash", phone=phone, proxy=proxy)


def _proxy(host: str = "1.2.3.4", port: int = 1080) -> ProxyConfig:
    return ProxyConfig(host=host, port=port)


def test_unproxied_phones_lists_only_accounts_without_a_proxy():
    accounts = [_account("+1", _proxy()), _account("+2"), _account("+3")]

    assert unproxied_phones(accounts) == ["+2", "+3"]


def test_ensure_all_proxied_passes_when_every_account_has_a_proxy():
    accounts = [_account("+1", _proxy()), _account("+2", _proxy())]

    ensure_all_proxied(accounts)  # should not raise


def test_ensure_all_proxied_raises_naming_unprotected_accounts():
    accounts = [_account("+1", _proxy()), _account("+2"), _account("+3")]

    with pytest.raises(UnprotectedAccountsError) as excinfo:
        ensure_all_proxied(accounts)

    assert excinfo.value.unproxied_phones == ["+2", "+3"]
    assert "+2" in str(excinfo.value)
    assert "+3" in str(excinfo.value)


def test_shared_proxy_groups_detects_accounts_on_the_same_exit():
    shared = _proxy("5.6.7.8", 1080)
    accounts = [
        _account("+1", shared),
        _account("+2", shared),
        _account("+3", _proxy("9.9.9.9", 1080)),
        _account("+4"),
    ]

    groups = shared_proxy_groups(accounts)

    assert len(groups) == 1
    (phones,) = groups.values()
    assert phones == ["+1", "+2"]


def test_shared_proxy_groups_ignores_unproxied_and_unique_proxies():
    accounts = [_account("+1", _proxy("1.1.1.1", 1)), _account("+2")]

    assert shared_proxy_groups(accounts) == {}


def test_ensure_no_shared_proxies_passes_when_every_proxy_is_distinct():
    accounts = [_account("+1", _proxy("1.1.1.1", 1)), _account("+2", _proxy("2.2.2.2", 1))]

    ensure_no_shared_proxies(accounts)  # should not raise


def test_ensure_no_shared_proxies_raises_naming_the_shared_group():
    shared = _proxy("5.6.7.8", 1080)
    accounts = [_account("+1", shared), _account("+2", shared), _account("+3", _proxy("9.9.9.9", 1))]

    with pytest.raises(SharedProxyError) as excinfo:
        ensure_no_shared_proxies(accounts)

    (phones,) = excinfo.value.groups.values()
    assert phones == ["+1", "+2"]
    assert "+1" in str(excinfo.value)
    assert "+2" in str(excinfo.value)
