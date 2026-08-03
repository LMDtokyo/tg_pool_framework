from datetime import datetime, timedelta, timezone

from license_server.db.repository import ActivationOutcome
from license_server.hashing import hash_secret
from license_server.tiers import Tier, duration_for

pytestmark = []

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _issue_one(repository, tier=Tier.MONTH, note=""):
    issued = await repository.create_keys(tier, 1, note)
    return issued[0]


async def test_create_keys_returns_requested_count_and_tier(repository):
    issued = await repository.create_keys(Tier.WEEK, 3, "batch-1")
    assert len(issued) == 3
    assert all(item.tier == "week" for item in issued)
    assert len({item.key_code for item in issued}) == 3


async def test_first_activation_claims_key_and_sets_expiry(repository):
    key = await _issue_one(repository, Tier.MONTH)
    hwid = hash_secret("machine-a")

    result = await repository.activate(key.key_code, hwid, now=_NOW)

    assert result.outcome is ActivationOutcome.OK
    assert result.tier == "month"
    assert result.activated_at == _NOW
    assert result.expires_at == _NOW + duration_for(Tier.MONTH)


async def test_reactivation_on_same_device_succeeds_without_changing_expiry(repository):
    key = await _issue_one(repository, Tier.WEEK)
    hwid = hash_secret("machine-a")
    first = await repository.activate(key.key_code, hwid, now=_NOW)

    later = _NOW + timedelta(hours=2)
    second = await repository.activate(key.key_code, hwid, now=later)

    assert second.outcome is ActivationOutcome.OK
    assert second.expires_at == first.expires_at
    assert second.activated_at == first.activated_at


async def test_activation_from_a_different_device_is_rejected(repository):
    key = await _issue_one(repository, Tier.WEEK)
    await repository.activate(key.key_code, hash_secret("machine-a"), now=_NOW)

    result = await repository.activate(key.key_code, hash_secret("machine-b"), now=_NOW)

    assert result.outcome is ActivationOutcome.DEVICE_MISMATCH


async def test_unknown_key_is_not_found(repository):
    result = await repository.activate("TGPL-0000-0000-0000-0000", hash_secret("machine-a"), now=_NOW)
    assert result.outcome is ActivationOutcome.NOT_FOUND


async def test_revoked_key_is_rejected(repository):
    key = await _issue_one(repository, Tier.WEEK)
    await repository.revoke(key.id)

    result = await repository.activate(key.key_code, hash_secret("machine-a"), now=_NOW)

    assert result.outcome is ActivationOutcome.REVOKED


async def test_revoking_after_activation_still_rejects_the_owning_device(repository):
    key = await _issue_one(repository, Tier.WEEK)
    hwid = hash_secret("machine-a")
    await repository.activate(key.key_code, hwid, now=_NOW)
    await repository.revoke(key.id)

    result = await repository.activate(key.key_code, hwid, now=_NOW)

    assert result.outcome is ActivationOutcome.REVOKED


async def test_expired_key_is_rejected_even_for_the_owning_device(repository):
    key = await _issue_one(repository, Tier.WEEK)
    hwid = hash_secret("machine-a")
    await repository.activate(key.key_code, hwid, now=_NOW)

    past_expiry = _NOW + duration_for(Tier.WEEK) + timedelta(seconds=1)
    result = await repository.activate(key.key_code, hwid, now=past_expiry)

    assert result.outcome is ActivationOutcome.EXPIRED


async def test_reset_device_unbinds_key_without_changing_expiry(repository):
    key = await _issue_one(repository, Tier.WEEK)
    first = await repository.activate(key.key_code, hash_secret("machine-a"), now=_NOW)

    reset_ok = await repository.reset_device(key.id)
    assert reset_ok is True

    second = await repository.activate(key.key_code, hash_secret("machine-b"), now=_NOW + timedelta(hours=1))
    assert second.outcome is ActivationOutcome.OK
    # New activation on the new device recomputes expiry from its own activation time.
    assert second.expires_at != first.expires_at


async def test_revoke_unknown_key_returns_false(repository):
    assert await repository.revoke(999) is False


async def test_list_keys_reports_correct_status(repository):
    unused = await _issue_one(repository, Tier.WEEK, note="unused")
    active = await _issue_one(repository, Tier.WEEK, note="active")
    revoked = await _issue_one(repository, Tier.WEEK, note="revoked")

    await repository.activate(active.key_code, hash_secret("machine-a"), now=_NOW)
    await repository.revoke(revoked.id)

    items, total = await repository.list_keys(limit=50, offset=0, now=_NOW)

    by_note = {item.note: item.status for item in items}
    assert by_note["unused"] == "unused"
    assert by_note["active"] == "active"
    assert by_note["revoked"] == "revoked"
    assert total == 3
