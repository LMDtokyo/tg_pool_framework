from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telethon.errors import (
    FloodWaitError,
    InputUserDeactivatedError,
    PeerFloodError,
    UserDeactivatedBanError,
    UserIsBlockedError,
)

from tg_pool.config import TimingPolicy
from tg_pool.resilience.circuit_breaker import CircuitBreaker, CircuitState
from tg_pool.messaging.messaging_service import (
    AdaptiveDelay,
    BatchReport,
    MessagePayload,
    SendResult,
    _AccountDeadError,
    _send_rich,
    _worker,
    render_template,
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

SIMPLE_PAYLOAD = MessagePayload(text="Test message", parse_mode=None)


def make_mock_client(send_side_effect=None, file_side_effect=None) -> MagicMock:
    client = MagicMock()
    client.send_message = AsyncMock(
        side_effect=send_side_effect,
        return_value=None if send_side_effect is None else ...,
    )
    client.send_file = AsyncMock(
        side_effect=file_side_effect,
        return_value=None if file_side_effect is None else ...,
    )
    client.forward_messages = AsyncMock(return_value=None)
    client.pin_message = AsyncMock()
    action_ctx = AsyncMock()
    action_ctx.__aenter__ = AsyncMock(return_value=None)
    action_ctx.__aexit__ = AsyncMock(return_value=False)
    client.action = MagicMock(return_value=action_ctx)
    return client


def make_adaptive() -> AdaptiveDelay:
    return AdaptiveDelay(FAST_POLICY)


def make_breaker() -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=10, recovery_timeout=60.0)


class TestSentinelPattern:
    async def test_sentinel_stops_single_worker(self):
        client = make_mock_client()
        task_queue: asyncio.Queue = asyncio.Queue()
        result_queue: asyncio.Queue = asyncio.Queue()

        await task_queue.put(None)

        await asyncio.wait_for(
            _worker(client, "+70001", task_queue, result_queue, SIMPLE_PAYLOAD, FAST_POLICY, None),
            timeout=2.0,
        )

        assert result_queue.empty()
        assert task_queue.empty()

    async def test_sentinel_stops_worker_after_real_tasks(self):
        client = make_mock_client()
        task_queue: asyncio.Queue = asyncio.Queue()
        result_queue: asyncio.Queue = asyncio.Queue()

        recipients = ["user_alpha", "user_beta", "user_gamma"]
        for r in recipients:
            await task_queue.put(r)
        await task_queue.put(None)

        with patch("tg_pool.messaging.messaging_service.asyncio.sleep", new=AsyncMock()):
            await asyncio.wait_for(
                _worker(client, "+70001", task_queue, result_queue, SIMPLE_PAYLOAD, FAST_POLICY, None),
                timeout=5.0,
            )

        assert result_queue.qsize() == len(recipients)
        assert task_queue.empty()

    async def test_multiple_sentinels_stop_multiple_workers(self):
        n_workers = 3
        clients = [make_mock_client() for _ in range(n_workers)]
        task_queue: asyncio.Queue = asyncio.Queue()
        result_queue: asyncio.Queue = asyncio.Queue()

        for r in {"a1", "a2", "a3", "a4", "a5"}:
            await task_queue.put(r)
        for _ in range(n_workers):
            await task_queue.put(None)

        coros = [
            _worker(c, f"+7000{i}", task_queue, result_queue, SIMPLE_PAYLOAD, FAST_POLICY, None)
            for i, c in enumerate(clients)
        ]
        await asyncio.wait_for(asyncio.gather(*coros), timeout=10.0)

        assert result_queue.qsize() == 5
        assert task_queue.empty()

    async def test_task_done_called_on_sentinel(self):
        client = make_mock_client()
        task_queue: asyncio.Queue = asyncio.Queue()
        result_queue: asyncio.Queue = asyncio.Queue()

        await task_queue.put(None)

        await asyncio.wait_for(
            _worker(client, "+70001", task_queue, result_queue, SIMPLE_PAYLOAD, FAST_POLICY, None),
            timeout=2.0,
        )

        await asyncio.wait_for(task_queue.join(), timeout=1.0)


class TestBatchReport:
    def test_record_success(self):
        report = BatchReport()
        report.record(SendResult("alice", "+7", True))
        assert report.total == 1
        assert report.succeeded == 1
        assert report.per_account["+7"] == 1

    def test_record_failure(self):
        report = BatchReport()
        report.record(SendResult("bob", "+7", False, error="Blocked"))
        assert report.failed == 1
        assert report.errors["bob"] == "Blocked"
        assert "+7" not in report.per_account

    def test_success_rate_zero_total(self):
        assert BatchReport().success_rate == 0.0

    def test_success_rate_full(self):
        report = BatchReport()
        for i in range(10):
            report.record(SendResult(f"u{i}", "+7", True))
        assert report.success_rate == 100.0

    def test_per_account_accumulates(self):
        report = BatchReport()
        for i in range(5):
            report.record(SendResult(f"u{i}", "+7001", True))
        for i in range(3):
            report.record(SendResult(f"v{i}", "+7002", True))
        assert report.per_account["+7001"] == 5
        assert report.per_account["+7002"] == 3

    def test_sent_recipients_tracks_successful_ones_only(self):
        report = BatchReport()
        report.record(SendResult("alice", "+7", True))
        report.record(SendResult("bob", "+7", False, error="Blocked"))
        assert report.sent_recipients == {"alice"}

    def test_merge_from_combines_totals(self):
        a = BatchReport(total=5, succeeded=4, failed=1, per_account={"+7001": 4}, sent_recipients={"alice"})
        b = BatchReport(total=3, succeeded=3, failed=0, per_account={"+7001": 1, "+7002": 2}, sent_recipients={"bob"})
        a.merge_from(b)
        assert a.total == 8
        assert a.succeeded == 7
        assert a.failed == 1
        assert a.per_account == {"+7001": 5, "+7002": 2}
        assert a.sent_recipients == {"alice", "bob"}

    def test_merge_from_combines_errors(self):
        a = BatchReport(errors={"alice": "Blocked"})
        b = BatchReport(errors={"bob": "PrivacyRestricted"})
        a.merge_from(b)
        assert a.errors == {"alice": "Blocked", "bob": "PrivacyRestricted"}


class TestSendRich:
    async def test_successful_send(self):
        client = make_mock_client()
        result = await _send_rich(
            client, "+7", "alice", SIMPLE_PAYLOAD, FAST_POLICY, make_adaptive(), make_breaker()
        )
        assert result.success is True
        assert result.recipient == "alice"
        client.send_message.assert_called_once_with(
            "alice", SIMPLE_PAYLOAD.text,
            parse_mode=SIMPLE_PAYLOAD.parse_mode,
            buttons=None,
            silent=False,
            link_preview=True,
            schedule=None,
        )

    async def test_flood_wait_retries_then_succeeds(self):
        call_count = 0

        async def side_effect(recipient, text, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                exc = FloodWaitError(request=None)
                exc.seconds = 0
                raise exc

        client = make_mock_client(send_side_effect=side_effect)
        result = await _send_rich(
            client, "+7", "bob", SIMPLE_PAYLOAD, FAST_POLICY, make_adaptive(), make_breaker()
        )
        assert result.success is True
        assert call_count == 3

    async def test_flood_wait_sleep_wakes_immediately_on_shutdown(self):
        """Regression: FloodWait back-off used to be a plain asyncio.sleep(), blocking shutdown until it elapsed."""
        async def side_effect(recipient, text, **kwargs):
            exc = FloodWaitError(request=None)
            exc.seconds = 30
            raise exc

        client = make_mock_client(send_side_effect=side_effect)
        shutdown_event = asyncio.Event()
        shutdown_event.set()

        # timeout margin is unrelated to the fix, just far below the 30s+ this would take unfixed
        result = await asyncio.wait_for(
            _send_rich(
                client, "+7", "grace", SIMPLE_PAYLOAD, FAST_POLICY,
                make_adaptive(), make_breaker(), shutdown_event=shutdown_event,
            ),
            timeout=8.0,
        )

        assert result.success is False
        assert result.error == "shutdown"
        assert client.send_message.call_count == 1  # no retry after shutdown fired

    async def test_user_is_blocked_returns_failure_no_retry(self):
        call_count = 0

        async def side_effect(recipient, text, **kwargs):
            nonlocal call_count
            call_count += 1
            raise UserIsBlockedError(request=None)

        client = make_mock_client(send_side_effect=side_effect)
        result = await _send_rich(
            client, "+7", "carol", SIMPLE_PAYLOAD, FAST_POLICY, make_adaptive(), make_breaker()
        )
        assert result.success is False
        assert "UserIsBlockedError" in result.error
        assert call_count == 1   # exactly one attempt

    async def test_user_deactivated_ban_raises_account_dead(self):
        async def side_effect(recipient, text, **kwargs):
            raise UserDeactivatedBanError(request=None)

        client = make_mock_client(send_side_effect=side_effect)
        with pytest.raises(_AccountDeadError):
            await _send_rich(
                client, "+7", "dave", SIMPLE_PAYLOAD, FAST_POLICY, make_adaptive(), make_breaker()
            )

    async def test_long_flood_wait_raises_account_dead(self):
        """FloodWait > _LONG_FLOOD_THRESHOLD seconds triggers failover."""
        from tg_pool.messaging.messaging_service import _LONG_FLOOD_THRESHOLD

        async def side_effect(recipient, text, **kwargs):
            exc = FloodWaitError(request=None)
            exc.seconds = _LONG_FLOOD_THRESHOLD + 1
            raise exc

        client = make_mock_client(send_side_effect=side_effect)
        with pytest.raises(_AccountDeadError, match="Long FloodWait"):
            await _send_rich(
                client, "+7", "eve", SIMPLE_PAYLOAD, FAST_POLICY, make_adaptive(), make_breaker()
            )

    async def test_peer_flood_raises_account_dead_without_retry(self):
        """PeerFlood has no retry-after value and must immediately trigger failover."""
        async def side_effect(recipient, text, **kwargs):
            raise PeerFloodError(request=None)

        client = make_mock_client(send_side_effect=side_effect)

        with pytest.raises(_AccountDeadError, match="peer-flood restricted"):
            await _send_rich(
                client, "+7", "flooded", SIMPLE_PAYLOAD,
                FAST_POLICY, make_adaptive(), make_breaker(),
            )

        assert client.send_message.call_count == 1

    async def test_repeated_short_flood_waits_trip_circuit_breaker(self):
        """Short FloodWaits that never cross _LONG_FLOOD_THRESHOLD still trip the breaker after failure_threshold hits."""
        policy = TimingPolicy(
            base_delay_sec=0.0, jitter_sec=0.0,
            inter_message_delay_sec=0.0, inter_message_jitter_sec=0.0,
            max_flood_retries=5, startup_jitter_max_sec=0.0,
        )

        async def side_effect(recipient, text, **kwargs):
            exc = FloodWaitError(request=None)
            exc.seconds = 0
            raise exc

        client = make_mock_client(send_side_effect=side_effect)
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)

        with pytest.raises(_AccountDeadError, match="Circuit breaker open"):
            await _send_rich(
                client, "+7", "frank", SIMPLE_PAYLOAD, policy, make_adaptive(), breaker
            )
        # Two recoverable FloodWaits recorded, third attempt short-circuits.
        assert client.send_message.call_count == 2

    async def test_generic_exception_resolves_half_open_breaker_instead_of_locking_it(self):
        """Regression: an unexpected exception used to leave a HALF_OPEN breaker's trial slot unresolved, locking it out forever."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05, half_open_max_calls=1)
        breaker.record_failure()  # CLOSED -> OPEN
        await asyncio.sleep(0.06)
        assert breaker.state == CircuitState.HALF_OPEN

        async def side_effect(recipient, text, **kwargs):
            raise RuntimeError("unexpected boom")

        client = make_mock_client(send_side_effect=side_effect)
        result = await _send_rich(
            client, "+7", "hank", SIMPLE_PAYLOAD, FAST_POLICY, make_adaptive(), breaker,
        )
        assert result.success is False

        # Reopened with a fresh recovery countdown, not permanently stuck.
        assert breaker.allow_request() is False
        await asyncio.sleep(0.06)
        assert breaker.allow_request() is True  # self-healed


class TestSendRichNewFeatures:
    async def test_spintax_resolved_before_send(self):
        client = make_mock_client()
        payload = MessagePayload(text="{Привет|Здравствуй}, мир!", parse_mode=None)

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        sent_text = client.send_message.call_args.args[1]
        assert sent_text in ("Привет, мир!", "Здравствуй, мир!")

    async def test_spintax_and_personalization_compose(self):
        client = make_mock_client()
        payload = MessagePayload(text="{Привет|Здравствуй}, {first_name}!", parse_mode=None)

        await _send_rich(
            client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker(),
            personalization_vars={"first_name": "Аня"},
        )

        sent_text = client.send_message.call_args.args[1]
        assert sent_text in ("Привет, Аня!", "Здравствуй, Аня!")

    async def test_silent_and_link_preview_passed_through(self):
        client = make_mock_client()
        payload = MessagePayload(text="Test", parse_mode=None, silent=True, link_preview=False)

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        client.send_message.assert_called_once_with(
            "alice", "Test", parse_mode=None, buttons=None, silent=True, link_preview=False,
            schedule=None,
        )

    async def test_media_paths_random_choice_used_over_media_path(self):
        client = make_mock_client()
        payload = MessagePayload(
            text="caption", parse_mode=None,
            media_path="should_not_be_used.jpg", media_paths=["a.jpg", "b.jpg"],
        )

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        sent_path = client.send_file.call_args.args[1]
        assert sent_path in ("a.jpg", "b.jpg")

    async def test_media_path_used_when_media_paths_not_set(self):
        client = make_mock_client()
        payload = MessagePayload(text="caption", parse_mode=None, media_path="only.jpg")

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        client.send_file.assert_called_once_with(
            "alice", "only.jpg", caption="caption", parse_mode=None, buttons=None, silent=False,
            schedule=None,
        )

    async def test_media_kind_video_note(self):
        client = make_mock_client()
        payload = MessagePayload(text="", parse_mode=None, media_path="round.mp4", media_kind="video_note")

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        _, kwargs = client.send_file.call_args
        assert kwargs["video_note"] is True

    async def test_media_kind_voice(self):
        client = make_mock_client()
        payload = MessagePayload(text="", parse_mode=None, media_path="note.ogg", media_kind="voice")

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        _, kwargs = client.send_file.call_args
        assert kwargs["voice_note"] is True

    async def test_media_kind_auto_has_no_special_flags(self):
        client = make_mock_client()
        payload = MessagePayload(text="", parse_mode=None, media_path="doc.pdf")

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        _, kwargs = client.send_file.call_args
        assert "video_note" not in kwargs
        assert "voice_note" not in kwargs


class TestSendRichForward:
    async def test_forward_link_forwards_instead_of_sending(self):
        client = make_mock_client()
        client.forward_messages = AsyncMock()
        payload = MessagePayload(text="", parse_mode=None, forward_link="t.me/pythondev/123")

        result = await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        assert result.success is True
        client.forward_messages.assert_called_once_with(
            "alice", 123, from_peer="pythondev", silent=False, schedule=None,
        )
        client.send_message.assert_not_called()

    async def test_forward_link_with_text_also_sends_followup_message(self):
        client = make_mock_client()
        client.forward_messages = AsyncMock()
        payload = MessagePayload(text="Check this out!", parse_mode=None, forward_link="t.me/pythondev/123")

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        client.forward_messages.assert_called_once()
        client.send_message.assert_called_once_with(
            "alice", "Check this out!", parse_mode=None, buttons=None, silent=False, link_preview=True,
            schedule=None,
        )

    async def test_bot_relay_forwards_one_of_the_configured_ids(self):
        client = make_mock_client()
        client.forward_messages = AsyncMock()
        payload = MessagePayload(
            text="", parse_mode=None, bot_relay_username="postbot", bot_relay_message_ids=[10, 20, 30],
        )

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        args, kwargs = client.forward_messages.call_args
        assert args[0] == "alice"
        assert args[1] in (10, 20, 30)
        assert kwargs["from_peer"] == "postbot"

    async def test_forward_takes_precedence_over_media(self):
        client = make_mock_client()
        client.forward_messages = AsyncMock()
        payload = MessagePayload(
            text="", parse_mode=None, media_path="photo.jpg", forward_link="t.me/pythondev/5",
        )

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        client.forward_messages.assert_called_once()
        client.send_file.assert_not_called()

    async def test_no_forward_source_configured_sends_normally(self):
        client = make_mock_client()
        client.forward_messages = AsyncMock()
        payload = MessagePayload(text="Hi", parse_mode=None)

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        client.forward_messages.assert_not_called()
        client.send_message.assert_called_once()


class TestSendRichScheduling:
    async def test_schedule_at_passed_to_send_message(self):
        client = make_mock_client()
        when = datetime(2030, 1, 1, 12, 0, 0)
        payload = MessagePayload(text="Hi", parse_mode=None, schedule_at=when)

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        _, kwargs = client.send_message.call_args
        assert kwargs["schedule"] == when

    async def test_schedule_at_passed_to_send_file(self):
        client = make_mock_client()
        when = datetime(2030, 1, 1, 12, 0, 0)
        payload = MessagePayload(text="", parse_mode=None, media_path="photo.jpg", schedule_at=when)

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        _, kwargs = client.send_file.call_args
        assert kwargs["schedule"] == when

    async def test_schedule_at_passed_to_forward_messages(self):
        client = make_mock_client()
        when = datetime(2030, 1, 1, 12, 0, 0)
        payload = MessagePayload(
            text="", parse_mode=None, forward_link="t.me/pythondev/123", schedule_at=when,
        )

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        _, kwargs = client.forward_messages.call_args
        assert kwargs["schedule"] == when

    async def test_no_schedule_at_defaults_to_none(self):
        client = make_mock_client()
        payload = MessagePayload(text="Hi", parse_mode=None)

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        _, kwargs = client.send_message.call_args
        assert kwargs["schedule"] is None

    async def test_typing_simulation_skipped_when_scheduled(self):
        client = make_mock_client()
        payload = MessagePayload(text="Hi", parse_mode=None, schedule_at=datetime(2030, 1, 1))

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        client.action.assert_not_called()

    async def test_typing_simulation_runs_when_not_scheduled(self):
        client = make_mock_client()
        payload = MessagePayload(text="Hi", parse_mode=None)

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        client.action.assert_called_once()


class TestSendRichPin:
    async def test_pin_after_send_pins_the_sent_message(self):
        client = make_mock_client()
        sent = MagicMock(name="sent_message")
        client.send_message = AsyncMock(return_value=sent)
        payload = MessagePayload(text="Hi", parse_mode=None, pin_after_send=True)

        result = await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        assert result.success is True
        client.pin_message.assert_called_once_with("alice", sent, notify=False)

    async def test_pin_not_requested_skips_pin(self):
        client = make_mock_client()
        payload = MessagePayload(text="Hi", parse_mode=None, pin_after_send=False)

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        client.pin_message.assert_not_called()

    async def test_pin_failure_does_not_fail_the_send(self):
        client = make_mock_client()
        client.pin_message = AsyncMock(side_effect=RuntimeError("no rights"))
        payload = MessagePayload(text="Hi", parse_mode=None, pin_after_send=True)

        result = await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        assert result.success is True

    async def test_pin_uses_last_message_when_forward_returns_a_list(self):
        client = make_mock_client()
        msg1, msg2 = MagicMock(name="msg1"), MagicMock(name="msg2")
        client.forward_messages = AsyncMock(return_value=[msg1, msg2])
        payload = MessagePayload(
            text="", parse_mode=None, forward_link="t.me/pythondev/123", pin_after_send=True,
        )

        await _send_rich(client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker())

        client.pin_message.assert_called_once_with("alice", msg2, notify=False)


class TestAdaptiveDelayWarmup:
    def test_default_multiplier_is_neutral(self):
        # TimingPolicy.next_message_delay() floors at 0.5s even with zero config.
        adaptive = AdaptiveDelay(FAST_POLICY)
        assert adaptive.next_message_delay() == pytest.approx(0.5)

    def test_warmup_multiplier_scales_delay(self):
        policy = TimingPolicy(
            base_delay_sec=0.0, jitter_sec=0.0,
            inter_message_delay_sec=2.0, inter_message_jitter_sec=0.0,
            max_flood_retries=3, startup_jitter_max_sec=0.0,
        )
        baseline = AdaptiveDelay(policy).next_message_delay()
        warmed = AdaptiveDelay(policy, warmup_multiplier=3.0).next_message_delay()
        assert warmed == pytest.approx(baseline * 3.0)


class _FakeDailyLimiter:
    def __init__(self, allowed: bool):
        self._allowed = allowed
        self.calls: list = []

    async def check_and_consume(self, user_id: str):
        self.calls.append(user_id)
        return self._allowed, "ok" if self._allowed else "rate_limited"


class TestWarmupDailyCap:
    async def test_daily_cap_reached_skips_send(self):
        client = make_mock_client()
        limiter = _FakeDailyLimiter(allowed=False)

        report = await send_notifications(
            workers=[(client, "+7001")],
            recipients={"alice"},
            payload=SIMPLE_PAYLOAD,
            policy=FAST_POLICY,
            warmup_limiters={"+7001": limiter},
        )

        client.send_message.assert_not_called()
        assert report.failed == 1
        assert report.errors["alice"] == "warmup_daily_cap_reached"
        assert limiter.calls == ["+7001"]

    async def test_daily_cap_not_reached_allows_send(self):
        client = make_mock_client()
        limiter = _FakeDailyLimiter(allowed=True)

        report = await send_notifications(
            workers=[(client, "+7001")],
            recipients={"alice"},
            payload=SIMPLE_PAYLOAD,
            policy=FAST_POLICY,
            warmup_limiters={"+7001": limiter},
        )

        client.send_message.assert_called_once()
        assert report.succeeded == 1

    async def test_no_warmup_limiters_behaves_as_before(self):
        client = make_mock_client()
        report = await send_notifications(
            workers=[(client, "+7001")],
            recipients={"alice"},
            payload=SIMPLE_PAYLOAD,
            policy=FAST_POLICY,
        )
        assert report.succeeded == 1


class TestRenderTemplate:
    def test_no_vars_returns_text_unchanged(self):
        assert render_template("Привет, {first_name}!", None) == "Привет, {first_name}!"

    def test_fills_known_placeholder(self):
        result = render_template("Привет, {first_name}!", {"first_name": "Иван"})
        assert result == "Привет, Иван!"

    def test_unknown_placeholder_left_literal_not_raised(self):
        result = render_template("Привет, {oops}!", {"first_name": "Иван"})
        assert result == "Привет, {oops}!"

    def test_empty_vars_dict_returns_text_unchanged(self):
        assert render_template("Привет, {first_name}!", {}) == "Привет, {first_name}!"


class TestSendRichPersonalization:
    async def test_send_rich_renders_personalized_text(self):
        client = make_mock_client()
        payload = MessagePayload(text="Привет, {first_name}!", parse_mode=None)

        await _send_rich(
            client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker(),
            personalization_vars={"first_name": "Мария"},
        )

        client.send_message.assert_called_once_with(
            "alice", "Привет, Мария!", parse_mode=None, buttons=None,
            silent=False, link_preview=True, schedule=None,
        )

    async def test_send_rich_without_personalization_sends_raw_text(self):
        client = make_mock_client()
        payload = MessagePayload(text="Привет!", parse_mode=None)

        await _send_rich(
            client, "+7", "alice", payload, FAST_POLICY, make_adaptive(), make_breaker(),
        )

        client.send_message.assert_called_once_with(
            "alice", "Привет!", parse_mode=None, buttons=None,
            silent=False, link_preview=True, schedule=None,
        )


class TestSendNotifications:
    async def test_empty_workers_returns_empty_report(self):
        report = await send_notifications(
            workers=[], recipients={"alice"},
            payload=SIMPLE_PAYLOAD, policy=FAST_POLICY,
        )
        assert report.total == 0

    async def test_empty_recipients_returns_empty_report(self):
        client = make_mock_client()
        report = await send_notifications(
            workers=[(client, "+7")], recipients=set(),
            payload=SIMPLE_PAYLOAD, policy=FAST_POLICY,
        )
        assert report.total == 0

    async def test_all_recipients_processed(self):
        recipients = {"u1", "u2", "u3", "u4", "u5"}
        workers = [(make_mock_client(), f"+700{i}") for i in range(2)]

        report = await send_notifications(
            workers=workers, recipients=recipients,
            payload=SIMPLE_PAYLOAD, policy=FAST_POLICY,
        )
        assert report.total == len(recipients)
        assert report.succeeded == len(recipients)
        assert report.failed == 0

    async def test_personalization_applied_end_to_end(self):
        client = make_mock_client()
        payload = MessagePayload(text="Привет, {first_name}!", parse_mode=None)

        await send_notifications(
            workers=[(client, "+7001")],
            recipients={"alice"},
            payload=payload,
            policy=FAST_POLICY,
            personalization={"alice": {"first_name": "Аня"}},
        )

        client.send_message.assert_called_once_with(
            "alice", "Привет, Аня!", parse_mode=None, buttons=None,
            silent=False, link_preview=True, schedule=None,
        )

    async def test_requeued_recipient_is_retried_by_idle_worker_after_account_death(self):
        calls = []

        async def fake_send(client, worker_phone, recipient, payload, policy, adaptive, breaker, **kwargs):
            calls.append((worker_phone, recipient))
            if worker_phone == "+dead":
                raise _AccountDeadError("Account peer-flood restricted: PeerFloodError")
            return SendResult(recipient=recipient, worker_phone=worker_phone, success=True)

        with patch("tg_pool.messaging.messaging_service._send_rich", side_effect=fake_send):
            report = await send_notifications(
                workers=[(make_mock_client(), "+dead"), (make_mock_client(), "+alive")],
                recipients={"alice"},
                payload=SIMPLE_PAYLOAD,
                policy=FAST_POLICY,
                worker_batch_size=1,
                worker_batch_delay_sec=0.01,
            )

        assert calls == [("+dead", "alice"), ("+alive", "alice")]
        assert report.succeeded == 1
        assert report.failed == 0
        assert report.per_account == {"+alive": 1}


class TestWorkerBatching:
    async def test_worker_batch_size_stages_worker_start(self, monkeypatch):
        sleep_calls = []

        async def spy(duration, shutdown_event):
            sleep_calls.append(duration)

        monkeypatch.setattr("tg_pool.messaging.messaging_service._interruptible_sleep", spy)

        workers = [(make_mock_client(), f"+700{i}") for i in range(4)]
        report = await send_notifications(
            workers=workers, recipients={"u1", "u2", "u3", "u4"},
            payload=SIMPLE_PAYLOAD, policy=FAST_POLICY,
            worker_batch_size=2, worker_batch_delay_sec=5.0,
        )

        assert sleep_calls.count(5.0) == 1  # 4 workers / batch 2 -> 2 groups -> 1 gap
        assert report.total == 4

    async def test_worker_batch_size_one_creates_n_minus_one_gaps(self, monkeypatch):
        sleep_calls = []

        async def spy(duration, shutdown_event):
            sleep_calls.append(duration)

        monkeypatch.setattr("tg_pool.messaging.messaging_service._interruptible_sleep", spy)

        workers = [(make_mock_client(), f"+700{i}") for i in range(3)]
        await send_notifications(
            workers=workers, recipients={"u1", "u2", "u3"},
            payload=SIMPLE_PAYLOAD, policy=FAST_POLICY,
            worker_batch_size=1, worker_batch_delay_sec=2.0,
        )

        assert sleep_calls.count(2.0) == 2

    async def test_batch_size_larger_than_pool_is_a_single_batch(self, monkeypatch):
        sleep_calls = []

        async def spy(duration, shutdown_event):
            sleep_calls.append(duration)

        monkeypatch.setattr("tg_pool.messaging.messaging_service._interruptible_sleep", spy)

        workers = [(make_mock_client(), f"+700{i}") for i in range(2)]
        await send_notifications(
            workers=workers, recipients={"u1", "u2"},
            payload=SIMPLE_PAYLOAD, policy=FAST_POLICY,
            worker_batch_size=10, worker_batch_delay_sec=3.0,
        )

        assert 3.0 not in sleep_calls

    async def test_no_batch_size_never_sleeps_the_batch_delay(self, monkeypatch):
        sleep_calls = []

        async def spy(duration, shutdown_event):
            sleep_calls.append(duration)

        monkeypatch.setattr("tg_pool.messaging.messaging_service._interruptible_sleep", spy)

        workers = [(make_mock_client(), f"+700{i}") for i in range(3)]
        await send_notifications(
            workers=workers, recipients={"u1", "u2", "u3"},
            payload=SIMPLE_PAYLOAD, policy=FAST_POLICY,
            worker_batch_delay_sec=5.0,  # worker_batch_size left at default (None)
        )

        assert 5.0 not in sleep_calls


class TestPerAccountQuota:
    async def test_quota_caps_successful_sends_per_worker(self):
        client = make_mock_client()
        recipients = {f"u{i}" for i in range(5)}

        report = await send_notifications(
            workers=[(client, "+7001")],
            recipients=recipients,
            payload=SIMPLE_PAYLOAD,
            policy=FAST_POLICY,
            messages_per_account_min=2,
            messages_per_account_max=2,
        )

        assert report.succeeded == 2
        # The other 3 never got a live worker to process them.
        assert report.total == 5
        assert report.failed == 3

    async def test_no_max_processes_all_recipients(self):
        client = make_mock_client()
        recipients = {f"u{i}" for i in range(5)}

        report = await send_notifications(
            workers=[(client, "+7001")],
            recipients=recipients,
            payload=SIMPLE_PAYLOAD,
            policy=FAST_POLICY,
        )

        assert report.succeeded == 5

    async def test_quota_is_random_within_configured_range(self, monkeypatch):
        captured_ranges = []
        real_randint = __import__("random").randint

        def spy_randint(lo, hi):
            captured_ranges.append((lo, hi))
            return real_randint(lo, hi)

        monkeypatch.setattr("tg_pool.messaging.messaging_service.random.randint", spy_randint)

        client = make_mock_client()
        await send_notifications(
            workers=[(client, "+7001")],
            recipients={"u1", "u2", "u3"},
            payload=SIMPLE_PAYLOAD,
            policy=FAST_POLICY,
            messages_per_account_min=1,
            messages_per_account_max=3,
        )

        assert captured_ranges == [(1, 3)]

    async def test_failed_sends_dont_count_toward_quota(self):
        blocked = {"u0", "u1"}

        async def side_effect(recipient, text, **kwargs):
            if recipient in blocked:
                raise UserIsBlockedError(request=None)

        client = make_mock_client(send_side_effect=side_effect)
        recipients = {f"u{i}" for i in range(5)}  # u0, u1 blocked; u2-u4 succeed

        report = await send_notifications(
            workers=[(client, "+7001")],
            recipients=recipients,
            payload=SIMPLE_PAYLOAD,
            policy=FAST_POLICY,
            messages_per_account_min=2,
            messages_per_account_max=2,
        )

        # Blocked recipients don't consume quota -- the worker keeps going
        # until it actually lands 2 successful sends (or runs out of queue).
        assert report.succeeded == 2
