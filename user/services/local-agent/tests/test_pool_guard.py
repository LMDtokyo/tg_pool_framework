"""tests/test_pool_guard.py — PoolAccessGuard mutual exclusion."""

import pytest

from tg_pool.api.pool_guard import PoolAccessGuard, PoolBusyError

pytestmark = pytest.mark.unit


def test_first_acquire_succeeds():
    guard = PoolAccessGuard()
    guard.try_acquire("campaign")
    assert guard.current_holder == "campaign"


def test_second_holder_raises_naming_current_holder():
    guard = PoolAccessGuard()
    guard.try_acquire("campaign")

    with pytest.raises(PoolBusyError, match="campaign"):
        guard.try_acquire("parsing")


def test_same_holder_can_reacquire():
    guard = PoolAccessGuard()
    guard.try_acquire("campaign")
    guard.try_acquire("campaign")  # must not raise
    assert guard.current_holder == "campaign"


def test_release_frees_the_guard():
    guard = PoolAccessGuard()
    guard.try_acquire("campaign")
    guard.release("campaign")
    assert guard.current_holder is None

    guard.try_acquire("parsing")  # must not raise now
    assert guard.current_holder == "parsing"


def test_release_by_wrong_holder_is_a_noop():
    guard = PoolAccessGuard()
    guard.try_acquire("campaign")
    guard.release("parsing")
    assert guard.current_holder == "campaign"


def test_release_when_nothing_held_is_a_noop():
    guard = PoolAccessGuard()
    guard.release("campaign")  # must not raise
    assert guard.current_holder is None
