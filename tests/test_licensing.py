"""tests/test_licensing.py — LicenseService (src/licensing/service.py) and the
local license state cache (src/db/license_repository.py)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.db.engine import build_engine_and_session_factory
from src.db.license_repository import LicenseStateRepository, StoredLicenseState, ensure_license_state_table
from src.db.models import Base
from src.licensing.client import (
    LicenseActivation,
    LicenseDeviceMismatchError,
    LicenseExpiredError,
    LicenseRevokedError,
    LicenseServerUnavailableError,
)
from src.licensing.service import LicenseService

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeLicenseServerClient:
    """Queue of canned outcomes: results/exceptions returned in call order."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    async def activate(self, license_key, hwid):
        self.calls.append((license_key, hwid))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _ok(tier="month", expires_at=None):
    return LicenseActivation(tier=tier, activated_at=_NOW, expires_at=expires_at or _NOW + timedelta(days=30))


def _service(outcomes, *, repository=None, revalidate_interval=timedelta(minutes=30), offline_grace=timedelta(hours=72)):
    client = _FakeLicenseServerClient(outcomes)
    service = LicenseService(
        client, repository, revalidate_interval=revalidate_interval, offline_grace=offline_grace
    )
    return service, client


async def test_is_active_starts_false_before_any_activation():
    service, _ = _service([])
    assert service.is_active() is False


async def test_successful_activation_makes_the_service_active():
    service, _ = _service([_ok(tier="year")])
    status = await service.activate("KEY", "hwid-1")
    assert status.valid is True
    assert status.tier == "year"
    assert service.is_active() is True


async def test_rejection_keeps_service_inactive_with_a_reason():
    service, _ = _service([LicenseExpiredError("expired")])
    status = await service.activate("KEY", "hwid-1")
    assert status.valid is False
    assert status.reason == "LicenseExpiredError"
    assert service.is_active() is False


async def test_device_mismatch_is_reported_and_leaves_service_inactive():
    service, _ = _service([LicenseDeviceMismatchError("taken")])
    status = await service.activate("KEY", "hwid-1")
    assert status.valid is False
    assert status.reason == "LicenseDeviceMismatchError"


async def test_network_failure_on_first_activation_fails_closed():
    service, _ = _service([LicenseServerUnavailableError("timeout")])
    status = await service.activate("KEY", "hwid-1")
    assert status.valid is False
    assert service.is_active() is False


async def test_network_failure_during_revalidation_rides_the_offline_grace():
    service, _ = _service([_ok(), LicenseServerUnavailableError("timeout")])
    await service.activate("KEY", "hwid-1")
    assert service.is_active() is True

    status = await service.activate("KEY", "hwid-1")  # simulates the periodic re-check
    assert status.valid is True  # still riding the grace window
    assert service.is_active() is True


async def test_definitive_rejection_immediately_revokes_a_previously_valid_state():
    service, _ = _service([_ok(), LicenseRevokedError("revoked")])
    await service.activate("KEY", "hwid-1")
    assert service.is_active() is True

    await service.activate("KEY", "hwid-1")  # e.g. the periodic re-check discovers a revocation
    assert service.is_active() is False


async def test_is_active_expires_once_revalidate_interval_and_grace_elapse():
    service, _ = _service(
        [_ok()],
        revalidate_interval=timedelta(milliseconds=30),
        offline_grace=timedelta(milliseconds=30),
    )
    await service.activate("KEY", "hwid-1")
    assert service.is_active() is True

    import asyncio

    await asyncio.sleep(0.1)
    assert service.is_active() is False


async def test_periodic_revalidation_reuses_the_last_activated_key_and_hwid():
    service, client = _service(
        [_ok(), _ok(), _ok(), _ok(), _ok()], revalidate_interval=timedelta(milliseconds=20)
    )
    await service.activate("KEY", "hwid-1")

    import asyncio

    task = asyncio.create_task(service.run_periodic_revalidation())
    await asyncio.sleep(0.06)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(client.calls) >= 2
    assert all(call == ("KEY", "hwid-1") for call in client.calls)


async def test_restore_cached_reactivates_without_a_network_call():
    class _StubRepository:
        async def load(self):
            return StoredLicenseState(
                license_key="KEY",
                hwid="hwid-1",
                tier="month",
                expires_at=_NOW + timedelta(days=10),
                last_validated_at=datetime.now(timezone.utc),
            )

    service, client = _service([], repository=_StubRepository())
    await service.restore_cached()

    assert service.is_active() is True
    assert client.calls == []


async def test_restore_cached_is_a_no_op_with_no_prior_activation():
    class _EmptyRepository:
        async def load(self):
            return None

    service, _ = _service([], repository=_EmptyRepository())
    await service.restore_cached()
    assert service.is_active() is False


# ------------------------------------------------------------------
# LicenseStateRepository — real SQLite round trip
# ------------------------------------------------------------------


@pytest.fixture
async def license_repository():
    engine, session_factory = build_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield LicenseStateRepository(session_factory)
    finally:
        await engine.dispose()


async def test_license_state_round_trips_through_sqlite(license_repository):
    state = StoredLicenseState(
        license_key="TGPL-AAAA-BBBB-CCCC-DDDD",
        hwid="hwid-1",
        tier="year",
        expires_at=_NOW + timedelta(days=365),
        last_validated_at=_NOW,
    )
    await license_repository.save(state)

    loaded = await license_repository.load()
    assert loaded.license_key == state.license_key
    assert loaded.tier == "year"


async def test_saving_again_overwrites_the_single_cached_row(license_repository):
    await license_repository.save(
        StoredLicenseState(
            license_key="KEY-1", hwid="hwid-1", tier="week",
            expires_at=_NOW + timedelta(days=7), last_validated_at=_NOW,
        )
    )
    await license_repository.save(
        StoredLicenseState(
            license_key="KEY-2", hwid="hwid-1", tier="year",
            expires_at=_NOW + timedelta(days=365), last_validated_at=_NOW,
        )
    )

    loaded = await license_repository.load()
    assert loaded.license_key == "KEY-2"
    assert loaded.tier == "year"


async def test_load_returns_none_when_never_activated(license_repository):
    assert await license_repository.load() is None


async def test_ensure_license_state_table_is_idempotent():
    engine, session_factory = build_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    try:
        await ensure_license_state_table(session_factory)
        await ensure_license_state_table(session_factory)  # must not raise on the second call
    finally:
        await engine.dispose()
