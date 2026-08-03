"""
tg_pool/api/events.py — WebSocket live event feed, decoupled from EventBus.publish().

EventBus.publish() (tg_pool/monitoring/event_bus.py) awaits each handler
sequentially and is called inline on the message-send hot path
(messaging_service.py). A WS handler that awaited websocket.send_json()
directly inside the bus callback would stall sending for the whole account
pool if one client connection were slow or stalled. Instead: the
bus-subscribed handler is synchronous and only enqueues onto a bounded
per-connection queue (dropping + logging on overflow instead of blocking);
a separate task drains that queue to the socket.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import asdict
from typing import Any, Tuple, Type

from fastapi import WebSocket, WebSocketDisconnect

from tg_pool.monitoring.event_bus import (
    AccountsDiscoveredEvent,
    AccountStatusEvent,
    EventBus,
    MessageDeliveredEvent,
    MetricUpdateEvent,
)

logger = logging.getLogger(__name__)

_QUEUE_MAXSIZE = 200
_FORWARDED_EVENTS: Tuple[Type[Any], ...] = (
    AccountStatusEvent,
    MessageDeliveredEvent,
    MetricUpdateEvent,
    AccountsDiscoveredEvent,
)


def _serialize(event: Any) -> dict:
    return {"type": type(event).__name__, "data": asdict(event)}


async def handle_event_stream(websocket: WebSocket, event_bus: EventBus) -> None:
    """Forwards AccountStatusEvent/MessageDeliveredEvent/MetricUpdateEvent to one WS client."""
    await websocket.accept()
    queue: "asyncio.Queue[Any]" = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)

    def _on_event(event: Any) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("WS event queue full — dropping %s", type(event).__name__)

    tokens = [event_bus.subscribe(event_type, _on_event) for event_type in _FORWARDED_EVENTS]

    async def _drain() -> None:
        while True:
            event = await queue.get()
            await websocket.send_json(_serialize(event))

    drain_task = asyncio.create_task(_drain(), name="ws-event-drain")
    try:
        # The client (launcher) only receives; this loop's sole purpose is to
        # detect disconnects, per FastAPI's documented WebSocket pattern.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        drain_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await drain_task
        for token in tokens:
            event_bus.unsubscribe(token)
