"""
tests/test_graceful_shutdown.py — Graceful Shutdown integration tests.

These tests verify the pipeline behaves correctly when a shutdown signal
is received mid-run: tasks are drained, resources are released, and no
coroutines hang indefinitely.

Scenarios:
  1.  Shutdown set BEFORE send starts → BatchReport has all tasks as failures
      with error="shutdown"; no actual sends occur.
  2.  Shutdown fires DURING sending → in-flight send finishes; remaining
      tasks are recorded as failures; no timeout / deadlock.
  3.  Shutdown fires during inter-message delay → delay is interrupted;
      worker exits promptly.
  4.  send_notifications with shutdown returns a BatchReport (not an exception).
  5.  Queue is fully drained after shutdown (no tasks_done() mismatch).
  6.  orchestrate() calls pool.close_all() after shutdown (finally block runs).
  7.  orchestrate() returns a partial BatchReport on shutdown, not an exception.
  8.  Extraction phase is cancelled when shutdown fires before extraction ends.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.config import TimingPolicy
from src.monitoring.event_bus import EventBus, MessageDeliveredEvent
from src.messaging.messaging_service import (
    BatchReport,
    MessagePayload,
    SendResult,
    _worker,
    send_notifications,
)

FAST_POLICY = TimingPolicy(
    base_delay_sec=0.0,
    jitter_sec=0.0,
    inter_message_delay_sec=0.0,
    inter_message_jitter_sec=0.0,
    max_flood_retries=3,
    startup_jitter_max_sec=0.0,
)

PAYLOAD = MessagePayload(text="test", parse_mode=None)


def make_client(delay: float = 0.0):
    """Mock client whose send_message takes `delay` seconds."""
    client = MagicMock()

    async def _send(recipient, text, **kwargs):
        if delay > 0:
            await asyncio.sleep(delay)

    client.send_message = AsyncMock(side_effect=_send)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__ = AsyncMock(return_value=False)
    client.action = MagicMock(return_value=ctx)
    return client


# ---------------------------------------------------------------------------
# 1-4: send_notifications with shutdown_event
# ---------------------------------------------------------------------------

class TestSendNotificationsShutdown:
    async def test_pre_set_shutdown_records_all_as_failures(self):
        """Shutdown already set before send starts: all tasks → failure, no sends."""
        shutdown = asyncio.Event()
        shutdown.set()

        client = make_client()
        recipients = {"u1", "u2", "u3"}

        with patch("src.messaging.messaging_service.asyncio.sleep", new=AsyncMock()):
            report = await send_notifications(
                workers=[(client, "+7")],
                recipients=recipients,
                payload=PAYLOAD,
                policy=FAST_POLICY,
                shutdown_event=shutdown,
            )

        assert report.total == len(recipients)
        assert report.succeeded == 0
        assert report.failed == len(recipients)
        # All errors must be "shutdown"
        assert all(v == "shutdown" for v in report.errors.values())
        # send_message must never have been called
        client.send_message.assert_not_called()

    async def test_mid_run_shutdown_partial_report_no_hang(self):
        """
        Shutdown fires while workers are between tasks.
        Pipeline completes without blocking; report contains partial results.
        """
        shutdown = asyncio.Event()
        recipients = {f"user{i}" for i in range(20)}

        send_count = 0

        async def slow_send(recipient, text, **kwargs):
            nonlocal send_count
            send_count += 1
            if send_count >= 3:
                # Fire shutdown after 3 sends
                shutdown.set()

        client = MagicMock()
        client.send_message = AsyncMock(side_effect=slow_send)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=None)
        ctx.__aexit__ = AsyncMock(return_value=False)
        client.action = MagicMock(return_value=ctx)

        with patch("src.messaging.messaging_service.asyncio.sleep", new=AsyncMock()):
            report = await asyncio.wait_for(
                send_notifications(
                    workers=[(client, "+7")],
                    recipients=recipients,
                    payload=PAYLOAD,
                    policy=FAST_POLICY,
                    shutdown_event=shutdown,
                ),
                timeout=10.0,
            )

        # All recipients accounted for (success + failure = total)
        assert report.total == len(recipients)
        assert report.succeeded + report.failed == report.total
        # Some succeeded before shutdown, rest failed as shutdown
        assert report.succeeded >= 1

    async def test_shutdown_returns_batch_report_not_exception(self):
        shutdown = asyncio.Event()
        shutdown.set()

        result = await send_notifications(
            workers=[(make_client(), "+7")],
            recipients={"a", "b"},
            payload=PAYLOAD,
            policy=FAST_POLICY,
            shutdown_event=shutdown,
        )

        assert isinstance(result, BatchReport)

    async def test_queue_fully_drained_after_shutdown(self):
        """
        After send_notifications returns, no pending tasks should remain
        in the internal queue.  We verify indirectly by checking task_done()
        balance: if the queue is not drained, the function would hang on
        queue.join() (if it were called), or the gather wouldn't complete.
        This test asserts the function returns within the timeout.
        """
        shutdown = asyncio.Event()
        shutdown.set()

        recipients = {f"u{i}" for i in range(50)}

        with patch("src.messaging.messaging_service.asyncio.sleep", new=AsyncMock()):
            report = await asyncio.wait_for(
                send_notifications(
                    workers=[(make_client(), "+7001"), (make_client(), "+7002")],
                    recipients=recipients,
                    payload=PAYLOAD,
                    policy=FAST_POLICY,
                    shutdown_event=shutdown,
                ),
                timeout=5.0,
            )

        assert report.total == len(recipients)


# ---------------------------------------------------------------------------
# 5: Interruptible inter-message delay
# ---------------------------------------------------------------------------

class TestInterruptibleDelay:
    async def test_shutdown_interrupts_inter_message_delay(self):
        """
        When shutdown fires during the inter-message sleep, the worker
        should wake up and exit promptly (not wait for the full delay).
        """
        shutdown = asyncio.Event()

        # Policy with a long inter-message delay
        slow_policy = TimingPolicy(
            base_delay_sec=0.0,
            jitter_sec=0.0,
            inter_message_delay_sec=60.0,   # 60s delay would hang the test
            inter_message_jitter_sec=0.0,
            max_flood_retries=1,
            startup_jitter_max_sec=0.0,
        )

        task_queue: asyncio.Queue = asyncio.Queue()
        result_queue: asyncio.Queue = asyncio.Queue()

        await task_queue.put("user_alpha")
        await task_queue.put(None)  # sentinel

        # Fire shutdown after first send completes
        client = make_client()
        original_send = client.send_message.side_effect

        async def send_then_shutdown(recipient, text, **kwargs):
            shutdown.set()

        client.send_message = AsyncMock(side_effect=send_then_shutdown)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=None)
        ctx.__aexit__ = AsyncMock(return_value=False)
        client.action = MagicMock(return_value=ctx)

        with patch("src.messaging.messaging_service.asyncio.sleep", new=AsyncMock()):
            await asyncio.wait_for(
                _worker(
                    client, "+7", task_queue, result_queue,
                    PAYLOAD, slow_policy, None,
                    shutdown_event=shutdown,
                ),
                timeout=5.0,
            )

        # Worker must have processed the task and exited
        result = result_queue.get_nowait()
        assert result.recipient == "user_alpha"


# ---------------------------------------------------------------------------
# 6-7: orchestrate() with shutdown
# ---------------------------------------------------------------------------

class TestOrchestrateShutdown:
    async def test_close_all_called_after_shutdown(self):
        """
        pool.close_all() must be called even when shutdown fires mid-pipeline.
        This verifies the finally block in orchestrate() always executes.
        """
        from src.orchestrator import orchestrate
        from src.config import AccountConfig

        shutdown = asyncio.Event()
        accounts = [AccountConfig(api_id=1, api_hash="h" * 32, phone="+7")]

        mock_pool = MagicMock()
        mock_pool.__bool__ = MagicMock(return_value=True)
        mock_pool.initialize = AsyncMock()
        mock_pool.close_all = AsyncMock()
        mock_pool.get_worker_pairs = MagicMock(return_value=[(MagicMock(), "+7")])

        shutdown.set()  # Set before orchestrate starts

        with (
            patch("src.orchestrator.ClientPool", return_value=mock_pool),
            patch("src.orchestrator.extract_members", new=AsyncMock(return_value=set())),
        ):
            report = await asyncio.wait_for(
                orchestrate(
                    accounts=accounts,
                    entity_identifier="@test",
                    shutdown_event=shutdown,
                ),
                timeout=5.0,
            )

        mock_pool.close_all.assert_called_once()
        assert isinstance(report, BatchReport)

    async def test_orchestrate_returns_partial_report_on_shutdown(self):
        """orchestrate() returns a BatchReport, never raises, even on shutdown."""
        from src.orchestrator import orchestrate
        from src.config import AccountConfig

        shutdown = asyncio.Event()
        accounts = [AccountConfig(api_id=1, api_hash="h" * 32, phone="+7")]

        mock_pool = MagicMock()
        mock_pool.__bool__ = MagicMock(return_value=True)
        mock_pool.initialize = AsyncMock()
        mock_pool.close_all = AsyncMock()
        mock_pool.get_worker_pairs = MagicMock(return_value=[(MagicMock(), "+7")])

        async def extract_with_shutdown(client, entity_identifier, policy):
            shutdown.set()
            return {"alice", "bob"}

        with (
            patch("src.orchestrator.ClientPool", return_value=mock_pool),
            patch("src.orchestrator.extract_members", side_effect=extract_with_shutdown),
            patch("src.orchestrator.send_notifications",
                  new=AsyncMock(return_value=BatchReport(total=2, succeeded=1, failed=1))),
        ):
            report = await asyncio.wait_for(
                orchestrate(
                    accounts=accounts,
                    entity_identifier="@test",
                    shutdown_event=shutdown,
                ),
                timeout=5.0,
            )

        assert isinstance(report, BatchReport)


# ---------------------------------------------------------------------------
# 8: Extraction phase cancellation
# ---------------------------------------------------------------------------

class TestExtractionCancellation:
    async def test_extraction_cancelled_when_shutdown_fires(self):
        """
        When shutdown fires while extract_members is running, orchestrate()
        must cancel extraction tasks and return an empty BatchReport without
        hanging or raising.
        """
        from src.orchestrator import orchestrate
        from src.config import AccountConfig

        shutdown = asyncio.Event()
        accounts = [AccountConfig(api_id=1, api_hash="h" * 32, phone="+7")]

        mock_pool = MagicMock()
        mock_pool.__bool__ = MagicMock(return_value=True)
        mock_pool.initialize = AsyncMock()
        mock_pool.close_all = AsyncMock()
        mock_pool.get_worker_pairs = MagicMock(return_value=[(MagicMock(), "+7")])

        async def slow_extraction(client, entity_identifier, policy):
            await asyncio.sleep(60)   # Would hang the test if not cancelled
            return {"alice"}

        async def trigger_shutdown():
            await asyncio.sleep(0.05)
            shutdown.set()

        with (
            patch("src.orchestrator.ClientPool", return_value=mock_pool),
            patch("src.orchestrator.extract_members", side_effect=slow_extraction),
        ):
            asyncio.create_task(trigger_shutdown())
            report = await asyncio.wait_for(
                orchestrate(
                    accounts=accounts,
                    entity_identifier="@test",
                    shutdown_event=shutdown,
                ),
                timeout=5.0,
            )

        # Extraction was cancelled; empty report (extraction returned no members)
        assert isinstance(report, BatchReport)
        assert report.total == 0
        mock_pool.close_all.assert_called_once()


# ---------------------------------------------------------------------------
# EventBus + shutdown integration
# ---------------------------------------------------------------------------

class TestEventBusShutdownIntegration:
    async def test_shutdown_events_published_to_bus(self):
        """
        When workers enter drain mode due to shutdown, they publish
        MessageDeliveredEvent(success=False, error='shutdown') to the bus.
        """
        bus = EventBus()
        delivered_events = []
        bus.subscribe(MessageDeliveredEvent, delivered_events.append)

        shutdown = asyncio.Event()
        shutdown.set()

        with patch("src.messaging.messaging_service.asyncio.sleep", new=AsyncMock()):
            report = await send_notifications(
                workers=[(make_client(), "+7")],
                recipients={"a1", "a2"},
                payload=PAYLOAD,
                policy=FAST_POLICY,
                event_bus=bus,
                shutdown_event=shutdown,
            )

        assert report.total == 2
        assert all(e.error == "shutdown" for e in delivered_events)
        assert len(delivered_events) == 2
