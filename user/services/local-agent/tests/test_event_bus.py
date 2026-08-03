"""
tests/test_event_bus.py — Unit tests for tg_pool/event_bus.py.

Scenarios:
  1.  Single sync handler receives published event.
  2.  Single async handler receives published event.
  3.  Multiple handlers on same event type all receive the event.
  4.  Handlers on different event types receive only their own events.
  5.  Unsubscribed handler no longer receives events.
  6.  unsubscribe() with unknown token is a no-op (no exception).
  7.  Handler exception is swallowed — other handlers still run.
  8.  Async handler exception is swallowed — other handlers still run.
  9.  Publishing with no subscribers is a no-op (no exception).
  10. Handler receives the exact event object published.
  11. subscribe() returns a unique token each time.
  12. Re-subscribing the same callable creates an independent subscription.
  13. AccountStatusEvent / MessageDeliveredEvent / MetricUpdateEvent round-trip.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_pool.monitoring.event_bus import (
    AccountStatusEvent,
    EventBus,
    MessageDeliveredEvent,
    MetricUpdateEvent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _AnotherEvent:
    """Unrelated event type for cross-type isolation tests."""


# ---------------------------------------------------------------------------
# Basic pub-sub
# ---------------------------------------------------------------------------

class TestBasicPubSub:
    async def test_sync_handler_receives_event(self):
        bus = EventBus()
        received = []
        bus.subscribe(AccountStatusEvent, received.append)

        evt = AccountStatusEvent(phone="+7", status="alive")
        await bus.publish(evt)

        assert received == [evt]

    async def test_async_handler_receives_event(self):
        bus = EventBus()
        received = []

        async def handler(evt):
            received.append(evt)

        bus.subscribe(MessageDeliveredEvent, handler)
        evt = MessageDeliveredEvent(worker_phone="+7", recipient="alice", success=True)
        await bus.publish(evt)

        assert received == [evt]

    async def test_multiple_handlers_all_receive_event(self):
        bus = EventBus()
        counters = [0, 0, 0]

        for i in range(3):
            idx = i
            bus.subscribe(MetricUpdateEvent, lambda e, _i=idx: counters.__setitem__(_i, 1))

        await bus.publish(MetricUpdateEvent(key="x", value=42))

        assert counters == [1, 1, 1]

    async def test_no_subscribers_is_a_noop(self):
        bus = EventBus()
        # Must not raise
        await bus.publish(AccountStatusEvent(phone="+7", status="dead"))

    async def test_publishing_wrong_type_does_not_trigger_handler(self):
        bus = EventBus()
        received = []
        bus.subscribe(AccountStatusEvent, received.append)

        await bus.publish(MetricUpdateEvent(key="k", value=1))

        assert received == []


# ---------------------------------------------------------------------------
# Cross-type isolation
# ---------------------------------------------------------------------------

class TestCrossTypeIsolation:
    async def test_handlers_receive_only_their_own_type(self):
        bus = EventBus()
        account_events = []
        metric_events = []

        bus.subscribe(AccountStatusEvent, account_events.append)
        bus.subscribe(MetricUpdateEvent, metric_events.append)

        acc_evt = AccountStatusEvent(phone="+7", status="alive")
        met_evt = MetricUpdateEvent(key="total", value=10)

        await bus.publish(acc_evt)
        await bus.publish(met_evt)

        assert account_events == [acc_evt]
        assert metric_events == [met_evt]

    async def test_unregistered_event_type_ignored(self):
        bus = EventBus()
        received = []
        bus.subscribe(AccountStatusEvent, received.append)

        await bus.publish(_AnotherEvent())

        assert received == []


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------

class TestUnsubscribe:
    async def test_unsubscribed_handler_no_longer_fires(self):
        bus = EventBus()
        received = []
        token = bus.subscribe(AccountStatusEvent, received.append)

        bus.unsubscribe(token)
        await bus.publish(AccountStatusEvent(phone="+7", status="alive"))

        assert received == []

    async def test_other_handler_survives_unsubscribe(self):
        bus = EventBus()
        first = []
        second = []

        token1 = bus.subscribe(AccountStatusEvent, first.append)
        bus.subscribe(AccountStatusEvent, second.append)

        bus.unsubscribe(token1)
        await bus.publish(AccountStatusEvent(phone="+7", status="flood"))

        assert first == []
        assert len(second) == 1

    async def test_double_unsubscribe_is_noop(self):
        bus = EventBus()
        token = bus.subscribe(AccountStatusEvent, lambda e: None)
        bus.unsubscribe(token)
        # Must not raise
        bus.unsubscribe(token)

    async def test_unknown_token_unsubscribe_is_noop(self):
        bus = EventBus()
        # Must not raise
        bus.unsubscribe(99999)


# ---------------------------------------------------------------------------
# Error isolation
# ---------------------------------------------------------------------------

class TestErrorIsolation:
    async def test_sync_handler_exception_does_not_crash_bus(self):
        bus = EventBus()
        second_called = []

        def bad_handler(evt):
            raise RuntimeError("intentional failure")

        bus.subscribe(AccountStatusEvent, bad_handler)
        bus.subscribe(AccountStatusEvent, lambda e: second_called.append(e))

        # Must not raise
        await bus.publish(AccountStatusEvent(phone="+7", status="banned"))

        assert len(second_called) == 1

    async def test_async_handler_exception_does_not_crash_bus(self):
        bus = EventBus()
        second_called = []

        async def bad_async_handler(evt):
            raise ValueError("intentional async failure")

        bus.subscribe(AccountStatusEvent, bad_async_handler)
        bus.subscribe(AccountStatusEvent, lambda e: second_called.append(e))

        await bus.publish(AccountStatusEvent(phone="+7", status="dead"))

        assert len(second_called) == 1


# ---------------------------------------------------------------------------
# Token uniqueness
# ---------------------------------------------------------------------------

class TestTokenUniqueness:
    def test_tokens_are_unique(self):
        bus = EventBus()
        tokens = [bus.subscribe(AccountStatusEvent, lambda e: None) for _ in range(10)]
        assert len(set(tokens)) == 10

    async def test_same_callable_subscribed_twice_fires_twice(self):
        bus = EventBus()
        received = []
        handler = received.append

        bus.subscribe(AccountStatusEvent, handler)
        bus.subscribe(AccountStatusEvent, handler)

        await bus.publish(AccountStatusEvent(phone="+7", status="alive"))

        assert len(received) == 2


# ---------------------------------------------------------------------------
# Event dataclass integrity
# ---------------------------------------------------------------------------

class TestEventDataclasses:
    async def test_account_status_event_round_trip(self):
        bus = EventBus()
        received = []
        bus.subscribe(AccountStatusEvent, received.append)

        evt = AccountStatusEvent(phone="+79001234567", status="spamblock", detail="@SpamBot")
        await bus.publish(evt)

        assert received[0].phone == "+79001234567"
        assert received[0].status == "spamblock"
        assert received[0].detail == "@SpamBot"

    async def test_message_delivered_event_round_trip(self):
        bus = EventBus()
        received = []
        bus.subscribe(MessageDeliveredEvent, received.append)

        evt = MessageDeliveredEvent(
            worker_phone="+7", recipient="bob", success=False, error="UserIsBlockedError"
        )
        await bus.publish(evt)

        assert received[0].success is False
        assert received[0].error == "UserIsBlockedError"

    async def test_metric_update_event_round_trip(self):
        bus = EventBus()
        received = []
        bus.subscribe(MetricUpdateEvent, received.append)

        await bus.publish(MetricUpdateEvent(key="total_recipients", value=500))

        assert received[0].key == "total_recipients"
        assert received[0].value == 500

    def test_events_are_frozen(self):
        evt = AccountStatusEvent(phone="+7", status="alive")
        with pytest.raises((AttributeError, TypeError)):
            evt.phone = "changed"  # type: ignore[misc]
