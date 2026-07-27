"""
tests/test_db_repository.py — AccountRepository round-trip tests.

Uses an in-memory SQLite (aiosqlite) engine as a lightweight stand-in for
Postgres — same SQLAlchemy Core surface, no network/service dependency.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.accounts.account_registry import AccountRegistry, RegistryEntry
from src.config import AccountConfig, ProxyConfig
from src.db.engine import build_engine_and_session_factory
from src.db.models import Base
from src.db.repository import AccountRepository
from src.accounts.health_checker import AccountState, AccountStatus

pytestmark = pytest.mark.unit


@pytest.fixture
async def repository():
    engine, session_factory = build_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield AccountRepository(session_factory)
    finally:
        await engine.dispose()


def _account(phone: str = "+79001234567") -> AccountConfig:
    return AccountConfig(
        api_id=123,
        api_hash="hash",
        phone=phone,
        proxy=ProxyConfig(host="1.2.3.4", port=1080, username="u", password="p"),
    )


async def test_upsert_then_load_all_round_trips_config_and_state(repository):
    entry = RegistryEntry(
        account=_account(),
        state=AccountState(
            status=AccountStatus.SPAMBLOCK,
            is_premium=True,
            restriction_expires=datetime.now(timezone.utc) + timedelta(hours=2),
            error_message="spamblocked",
            username="ivan",
            first_name="Ivan",
        ),
        last_checked=datetime.now(timezone.utc),
    )

    await repository.upsert(entry)
    loaded = await repository.load_all()

    assert len(loaded) == 1
    got = loaded[0]
    assert got.account.phone == entry.account.phone
    assert got.account.proxy.host == "1.2.3.4"
    assert got.state.status == AccountStatus.SPAMBLOCK
    assert got.state.is_premium is True
    assert got.state.username == "ivan"


async def test_first_seen_round_trips_via_created_at(repository):
    phone = "+79222222222"
    await repository.upsert(RegistryEntry(account=_account(phone), state=None))

    loaded = await repository.load_all()
    entry = next(e for e in loaded if e.account.phone == phone)
    assert entry.first_seen is not None


async def test_first_seen_survives_repeated_upserts(repository):
    """created_at (and therefore first_seen) must not reset on ON CONFLICT DO UPDATE."""
    phone = "+79333333333"
    await repository.upsert(RegistryEntry(account=_account(phone), state=None))
    first_load = await repository.load_all()
    original_first_seen = next(e for e in first_load if e.account.phone == phone).first_seen

    await repository.upsert(RegistryEntry(
        account=_account(phone),
        state=AccountState(status=AccountStatus.ALIVE),
    ))
    second_load = await repository.load_all()
    updated_first_seen = next(e for e in second_load if e.account.phone == phone).first_seen

    assert updated_first_seen == original_first_seen


async def test_proxy_type_round_trips(repository):
    phone = "+79666666666"
    account = AccountConfig(
        api_id=1, api_hash="h", phone=phone,
        proxy=ProxyConfig(host="1.2.3.4", port=8080, proxy_type="http"),
    )
    await repository.upsert(RegistryEntry(account=account, state=None))

    loaded = await repository.load_all()
    got = next(e for e in loaded if e.account.phone == phone)

    assert got.account.proxy.proxy_type == "http"


async def test_proxy_type_defaults_to_socks5_without_proxy(repository):
    phone = "+79777777777"
    account = AccountConfig(api_id=1, api_hash="h", phone=phone, proxy=None)
    await repository.upsert(RegistryEntry(account=account, state=None))

    loaded = await repository.load_all()
    got = next(e for e in loaded if e.account.phone == phone)

    assert got.account.proxy is None


async def test_geo_2fa_role_folder_round_trip(repository):
    phone = "+79444444444"
    entry = RegistryEntry(
        account=_account(phone),
        state=AccountState(status=AccountStatus.ALIVE, country="RU", has_2fa=True),
        role="sender",
        folder="batch-1",
    )

    await repository.upsert(entry)
    loaded = await repository.load_all()
    got = next(e for e in loaded if e.account.phone == phone)

    assert got.state.country == "RU"
    assert got.state.has_2fa is True
    assert got.role == "sender"
    assert got.folder == "batch-1"


async def test_role_and_folder_default_to_empty_string(repository):
    phone = "+79555555555"
    await repository.upsert(RegistryEntry(account=_account(phone), state=None))

    loaded = await repository.load_all()
    got = next(e for e in loaded if e.account.phone == phone)

    assert got.role == ""
    assert got.folder == ""


async def test_upsert_is_idempotent_per_phone(repository):
    phone = "+79000000000"
    await repository.upsert(RegistryEntry(account=_account(phone), state=None))
    await repository.upsert(RegistryEntry(
        account=_account(phone),
        state=AccountState(status=AccountStatus.ALIVE),
    ))

    loaded = await repository.load_all()
    assert len(loaded) == 1
    assert loaded[0].state.status == AccountStatus.ALIVE


async def test_registry_survives_reload_via_repository(repository):
    registry = AccountRegistry(repository=repository)
    await registry.register(_account("+79111111111"))
    await registry.update_state(
        "+79111111111",
        AccountState(status=AccountStatus.FROZEN, error_message="frozen"),
    )

    await registry.close()

    fresh_registry = AccountRegistry(repository=repository)
    await fresh_registry.load_from_repository()

    entry = fresh_registry.get("+79111111111")
    assert entry is not None
    assert entry.state.status == AccountStatus.FROZEN
