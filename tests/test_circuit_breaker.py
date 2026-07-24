"""tests/test_circuit_breaker.py — CircuitBreaker state machine."""

import time

import pytest

from src.resilience.circuit_breaker import CircuitBreaker, CircuitState

pytestmark = pytest.mark.unit


def test_starts_closed_and_allows_requests():
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_trips_open_after_failure_threshold():
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False


def test_success_resets_failure_count_while_closed():
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED  # only 2 consecutive since the reset


def test_transitions_to_half_open_after_recovery_timeout():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.02)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    time.sleep(0.15)
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.allow_request() is True


def test_half_open_limits_trial_calls():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.02, half_open_max_calls=1)
    breaker.record_failure()
    time.sleep(0.15)

    assert breaker.allow_request() is True   # the one trial call
    assert breaker.allow_request() is False  # no more slots until resolved


def test_half_open_success_closes_breaker():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.02)
    breaker.record_failure()
    time.sleep(0.15)

    breaker.allow_request()
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_half_open_failure_reopens_breaker():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.02)
    breaker.record_failure()
    time.sleep(0.15)

    breaker.allow_request()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False


def test_constructor_rejects_invalid_thresholds():
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreaker(half_open_max_calls=0)
