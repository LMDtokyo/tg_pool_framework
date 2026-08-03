"""
tg_pool/resilience/circuit_breaker.py — Generic 3-state circuit breaker.

Replaces the ad hoc "is this account dead" logic that used to be split across
_LONG_FLOOD_THRESHOLD, _AccountDeadError, and FailoverCoordinator with one
reusable, independently-testable state machine. Domain code decides what
counts as success/failure (see messaging_service.py); this class only tracks
the state transitions.
"""

from __future__ import annotations

import time
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Standard closed -> open -> half-open -> closed breaker.

    CLOSED:    requests flow; `failure_threshold` consecutive failures trip it OPEN.
    OPEN:      requests are rejected until `recovery_timeout` seconds have passed.
    HALF_OPEN: up to `half_open_max_calls` trial requests are allowed; a success
               closes the breaker, a failure reopens it.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")

        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        self._maybe_transition_to_half_open()
        return self._state

    def allow_request(self) -> bool:
        """Whether a new call should be attempted right now."""
        self._maybe_transition_to_half_open()

        if self._state is CircuitState.OPEN:
            return False
        if self._state is CircuitState.HALF_OPEN:
            if self._half_open_calls >= self._half_open_max_calls:
                return False
            self._half_open_calls += 1
            return True
        return True  # CLOSED

    def record_success(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            self._close()
        else:
            self._failure_count = 0

    def record_failure(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            self._open()
            return

        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._open()

    # ------------------------------------------------------------------
    # Internal transitions
    # ------------------------------------------------------------------

    def _maybe_transition_to_half_open(self) -> None:
        if self._state is CircuitState.OPEN and (
            time.monotonic() - self._opened_at >= self._recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._half_open_calls = 0

    def _close(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
