"""
src/accounts/proxy_safety.py — Guards against silently routing risky bulk
actions (mass send, invite, engagement) through the operator's own real IP.

An account with proxy=None connects to Telegram directly from the machine
running this program (see ClientFactory.build in connection_manager.py).
Doing that at bulk-action volume risks getting the operator's own network
flagged by Telegram, which can cascade into every account sharing that exit
identity getting banned together -- including, if it was the operator's real
IP, their own personal Telegram usage on the same network. Reusing one proxy
across many accounts (ProxyAllocator's round-robin, src/accounts/account_loader.py)
carries the same correlation risk one step removed.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from src.config import AccountConfig


class UnprotectedAccountsError(ValueError):
    """Raised when require_proxy=True and one or more selected senders have no proxy."""

    def __init__(self, unproxied_phones: List[str]) -> None:
        self.unproxied_phones = unproxied_phones
        super().__init__(
            "These accounts have no proxy assigned and would connect directly "
            "from this machine: "
            f"{', '.join(unproxied_phones)}. Assign a proxy to them or disable "
            "require_proxy to run anyway."
        )


def unproxied_phones(accounts: Iterable[AccountConfig]) -> List[str]:
    """Phones (input order) whose account has no assigned proxy."""
    return [account.phone for account in accounts if account.proxy is None]


def shared_proxy_groups(accounts: Iterable[AccountConfig]) -> Dict[str, List[str]]:
    """
    Groups phones by identical (proxy_type, host, port, username) -- reveals
    accounts silently sharing one exit IP via ProxyAllocator's round-robin
    reuse. Unproxied accounts and groups of size 1 (no sharing) are excluded;
    use unproxied_phones() for the former.
    """
    groups: Dict[str, List[str]] = {}
    for account in accounts:
        if account.proxy is None:
            continue
        key = (
            f"{account.proxy.proxy_type}:{account.proxy.host}:"
            f"{account.proxy.port}:{account.proxy.username or ''}"
        )
        groups.setdefault(key, []).append(account.phone)
    return {key: phones for key, phones in groups.items() if len(phones) > 1}


def ensure_all_proxied(accounts: Iterable[AccountConfig]) -> None:
    """Raises UnprotectedAccountsError if any given account has no proxy."""
    missing = unproxied_phones(accounts)
    if missing:
        raise UnprotectedAccountsError(missing)
