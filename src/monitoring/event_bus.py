"""
src/event_bus.py — Asynchronous Pub-Sub event bus.

Events are plain frozen dataclasses. Handlers may be sync callables or
coroutine functions — publish() normalises both.  Handler exceptions are
caught and logged so one broken subscriber can never crash the publisher.

Canonical events:
  AccountStatusEvent   — account health changed (alive/dead/flood/spamblock)
  MessageDeliveredEvent — a single send attempt finished (success or failure)
  MetricUpdateEvent     — arbitrary pipeline metric update (key/value)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Any]  # sync or async


# ---------------------------------------------------------------------------
# Public event types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AccountStatusEvent:
    """
    Emitted when an account's operational status changes.

    status values:
      "alive"      — authorized and responding normally
      "dead"       — hard ban, auth key revoked, or UserDeactivated
      "flood"      — FloodWaitError beyond the long-wait threshold
      "spamblock"  — @SpamBot reports active restriction
      "proxy_dead" — proxy unreachable
    """
    phone: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class MessageDeliveredEvent:
    """Emitted after every send attempt — both success and failure."""
    worker_phone: str
    recipient: str
    success: bool
    error: str = ""


@dataclass(frozen=True)
class MetricUpdateEvent:
    """Generic pipeline metric (total_recipients, phase transitions, etc.)."""
    key: str
    value: Any


@dataclass(frozen=True)
class ScriptReloadedEvent:
    """Emitted by LuaEngine.watch() when a .lua script is (re)compiled from disk."""
    script_name: str


@dataclass(frozen=True)
class AccountsDiscoveredEvent:
    """
    Emitted by AccountDiscoveryPoller (src/accounts/discovery_poller.py) after a
    background sweep of ACCOUNTS_DIR/SPARE_ACCOUNTS_DIR/TDATA_ACCOUNTS_DIR finds
    something new -- an operator who just dropped a purchased account base into
    the folder doesn't have to notice on their own or click Refresh.
    """
    loaded_count: int
    loaded_phones: list
    failed_count: int
    failed_reasons: list  # ["79161234567.session: no .json companion...", ...]


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

class EventBus:
    """
    Async Pub-Sub event bus.

    Handlers are invoked sequentially in subscription order per event type.
    Async handlers are awaited; sync handlers are called directly.
    A handler that raises is logged and skipped — it never affects other handlers
    or the publisher.

    Usage:
        bus = EventBus()
        token = bus.subscribe(MessageDeliveredEvent, my_handler)
        await bus.publish(MessageDeliveredEvent(...))
        bus.unsubscribe(token)
    """

    def __init__(self) -> None:
        # event_type → {token: handler}
        self._handlers: Dict[type, Dict[int, Handler]] = {}
        # token → event_type (for O(1) unsubscribe)
        self._token_to_type: Dict[int, type] = {}
        self._counter: int = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def subscribe(self, event_type: type, handler: Handler) -> int:
        """
        Register handler to receive events of event_type.

        Returns an integer subscription token that can be passed to
        unsubscribe() to remove the handler later.
        """
        token = self._counter
        self._counter += 1
        self._handlers.setdefault(event_type, {})[token] = handler
        self._token_to_type[token] = event_type
        return token

    def unsubscribe(self, token: int) -> None:
        """
        Remove a handler by its subscription token.

        No-op if the token has already been removed or never existed.
        """
        event_type = self._token_to_type.pop(token, None)
        if event_type is not None:
            self._handlers.get(event_type, {}).pop(token, None)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, event: Any) -> None:
        """
        Dispatch event to all registered handlers for its type.

        Handlers run sequentially.  A handler that raises is logged and
        skipped without affecting subsequent handlers or the caller.
        """
        handlers = list(self._handlers.get(type(event), {}).values())
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception(
                    "EventBus: handler %r raised on %r — skipped.",
                    handler, event,
                )
