from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    InputUserDeactivatedError,
    PeerFloodError,
    PeerIdInvalidError,
    UserDeactivatedBanError,
    UserDeactivatedError,
    UserIsBlockedError,
    UserPrivacyRestrictedError,
)
from telethon.tl.custom import Button

from src.config import TimingPolicy
from src.messaging.forward_source import resolve_forward_source
from src.messaging.spintax import resolve_spintax
from src.monitoring.event_bus import AccountStatusEvent, EventBus, MessageDeliveredEvent
from src.resilience.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    from src.messaging.lua_storage import RedisRateLimiter
    from src.orchestrator import FailoverCoordinator

logger = logging.getLogger(__name__)

_SENTINEL = None

_BUTTON_RE = re.compile(r"\[([^\|\]]+)\|([^\]]+)\]")

_LONG_FLOOD_THRESHOLD = 300

_TYPING_MIN = 2.0
_TYPING_MAX = 4.0

# N consecutive FloodWaits within one worker (even below _LONG_FLOOD_THRESHOLD each) is
# treated as the account being dead -- same _AccountDeadError / failover path as a hard ban.
_BREAKER_FAILURE_THRESHOLD = 3
_BREAKER_RECOVERY_TIMEOUT = 60.0


class _AccountDeadError(Exception):
    """Raised when the account itself is dead or rate-limited beyond recovery."""


@dataclass
class MessagePayload:
    """text supports spintax {a|b} (resolved before {username} placeholders); media_paths overrides media_path; forward_link (t.me/...) or bot_relay_username+bot_relay_message_ids forwards an existing post instead of sending text/media, with non-empty text sent as a follow-up. schedule_at, if set, makes every send a Telethon-scheduled message (success means "accepted for scheduling", not "delivered"); pin_after_send pins the just-(scheduled-)sent message in each recipient's chat."""
    text: str
    media_path: Optional[str] = None
    media_paths: Optional[List[str]] = None
    media_kind: str = "auto"
    buttons_raw: Optional[str] = None
    parse_mode: Optional[str] = "markdown"
    silent: bool = False
    link_preview: bool = True
    forward_link: Optional[str] = None
    bot_relay_username: Optional[str] = None
    bot_relay_message_ids: Optional[List[int]] = None
    schedule_at: Optional[datetime] = None
    pin_after_send: bool = False


class _SafeDict(dict):
    """Leaves unknown format_map() placeholders as literal text ("{oops}") instead of raising KeyError, so a template typo can't crash the send pipeline."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_template(text: str, personalization_vars: Optional[Dict[str, str]]) -> str:
    """Fill {first_name}/{username}/etc. placeholders; returns text unchanged if no vars."""
    if not personalization_vars:
        return text
    return text.format_map(_SafeDict(personalization_vars))


def parse_buttons(raw: str) -> Optional[List[List[Button]]]:
    """Parses "[Label|url] [Label2|url2]" (rows separated by newlines) into a Telethon 2-D button list; returns None if no valid buttons are found."""
    if not raw or not raw.strip():
        return None

    rows: List[List[Button]] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        row_buttons: List[Button] = []
        for match in _BUTTON_RE.finditer(line):
            label = match.group(1).strip()
            url = match.group(2).strip()
            if label and url.startswith("http"):
                row_buttons.append(Button.url(label, url))
        if row_buttons:
            rows.append(row_buttons)

    return rows if rows else None


class AdaptiveDelay:
    """Exponential backoff of the inter-message delay based on FloodWait hits: delay = min(base * 2^hits, cap), decaying back to base after a clean streak."""

    _BACKOFF_CAP = 60.0
    _DECAY_AFTER = 10

    def __init__(self, policy: TimingPolicy, warmup_multiplier: float = 1.0) -> None:
        self._policy = policy
        self._flood_hits = 0
        self._clean_streak = 0
        # >1.0 for accounts still ramping up (WarmupPolicy); shares the flood backoff cap
        # rather than a second uncapped path.
        self._warmup_multiplier = warmup_multiplier

    def record_flood(self) -> None:
        self._flood_hits = min(self._flood_hits + 1, 6)
        self._clean_streak = 0

    def record_clean(self) -> None:
        self._clean_streak += 1
        if self._clean_streak >= self._DECAY_AFTER and self._flood_hits > 0:
            self._flood_hits -= 1
            self._clean_streak = 0

    def next_message_delay(self) -> float:
        base = self._policy.next_message_delay() * self._warmup_multiplier
        return min(base * (2 ** self._flood_hits), self._BACKOFF_CAP)

    def next_delay(self) -> float:
        return self._policy.next_delay()


async def _interruptible_sleep(
    duration: float, shutdown_event: Optional[asyncio.Event]
) -> None:
    """Sleep for `duration`, waking immediately if shutdown_event fires first."""
    if duration <= 0:
        return
    if shutdown_event is None:
        await asyncio.sleep(duration)
        return
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=duration)
    except asyncio.TimeoutError:
        pass


async def _simulate_action(client: TelegramClient, peer: str, has_media: bool) -> None:
    action_type = "upload_photo" if has_media else "typing"
    duration = random.uniform(_TYPING_MIN, _TYPING_MAX)
    try:
        async with client.action(peer, action_type):
            await asyncio.sleep(duration)
    except Exception:
        await asyncio.sleep(duration)


async def _send_rich(
    client: TelegramClient,
    worker_phone: str,
    recipient: str,
    payload: MessagePayload,
    policy: TimingPolicy,
    adaptive: AdaptiveDelay,
    breaker: CircuitBreaker,
    personalization_vars: Optional[Dict[str, str]] = None,
    shutdown_event: Optional[asyncio.Event] = None,
) -> "SendResult":
    """Raises _AccountDeadError for account-level failures (triggers failover); returns SendResult for recipient-level failures. Each attempt fails fast via breaker.allow_request() if the circuit is OPEN; personalization_vars are rendered into text once and reused across retries, and shutdown_event wakes an in-progress FloodWait sleep immediately."""
    buttons = parse_buttons(payload.buttons_raw) if payload.buttons_raw else None
    # Spintax resolves per-recipient before {username} substitution; retries reuse the same rendered text.
    text = render_template(resolve_spintax(payload.text), personalization_vars)
    media_path = random.choice(payload.media_paths) if payload.media_paths else payload.media_path
    forward_source = resolve_forward_source(
        payload.forward_link, payload.bot_relay_username, payload.bot_relay_message_ids,
    )

    for attempt in range(1, policy.max_flood_retries + 1):
        if not breaker.allow_request():
            raise _AccountDeadError("Circuit breaker open — account excluded until recovery")

        try:
            if payload.schedule_at is None:
                await _simulate_action(client, recipient, has_media=bool(media_path or forward_source))

            sent_message = None
            if forward_source is not None:
                peer, message_id = forward_source
                sent_message = await client.forward_messages(
                    recipient, message_id, from_peer=peer,
                    silent=payload.silent, schedule=payload.schedule_at,
                )
                if text.strip():
                    sent_message = await client.send_message(
                        recipient,
                        text,
                        parse_mode=payload.parse_mode,
                        buttons=buttons,
                        silent=payload.silent,
                        link_preview=payload.link_preview,
                        schedule=payload.schedule_at,
                    )
            elif media_path:
                send_file_kwargs: Dict[str, object] = dict(
                    caption=text,
                    parse_mode=payload.parse_mode,
                    buttons=buttons,
                    silent=payload.silent,
                    schedule=payload.schedule_at,
                )
                if payload.media_kind == "video_note":
                    send_file_kwargs["video_note"] = True
                elif payload.media_kind == "voice":
                    send_file_kwargs["voice_note"] = True
                sent_message = await client.send_file(recipient, media_path, **send_file_kwargs)
            else:
                sent_message = await client.send_message(
                    recipient,
                    text,
                    parse_mode=payload.parse_mode,
                    buttons=buttons,
                    silent=payload.silent,
                    link_preview=payload.link_preview,
                    schedule=payload.schedule_at,
                )

            if payload.pin_after_send and sent_message is not None:
                try:
                    pin_target = sent_message[-1] if isinstance(sent_message, list) else sent_message
                    await client.pin_message(recipient, pin_target, notify=False)
                except Exception as pin_exc:
                    logger.warning("[%s] Pin failed for @%s: %s", worker_phone, recipient, pin_exc)

            logger.info("[%s] ✓ @%s (attempt %d)", worker_phone, recipient, attempt)
            adaptive.record_clean()
            breaker.record_success()
            return SendResult(recipient=recipient, worker_phone=worker_phone, success=True)

        except FloodWaitError as exc:
            if exc.seconds > _LONG_FLOOD_THRESHOLD:
                breaker.record_failure()
                raise _AccountDeadError(
                    f"Long FloodWait: {exc.seconds}s > {_LONG_FLOOD_THRESHOLD}s threshold"
                )
            wait = exc.seconds + adaptive.next_delay()
            adaptive.record_flood()
            breaker.record_failure()
            logger.warning(
                "[%s] FloodWait @%s: %.1fs (attempt %d/%d)",
                worker_phone, recipient, wait, attempt, policy.max_flood_retries,
            )
            if attempt >= policy.max_flood_retries:
                return SendResult(
                    recipient=recipient, worker_phone=worker_phone, success=False,
                    error=f"FloodWait exhausted after {exc.seconds}s",
                )
            await _interruptible_sleep(wait, shutdown_event)
            if shutdown_event is not None and shutdown_event.is_set():
                return SendResult(
                    recipient=recipient, worker_phone=worker_phone, success=False,
                    error="shutdown",
                )

        except PeerFloodError as exc:
            # Unlike FloodWaitError, Telegram provides no retry-after duration for
            # PeerFloodError.  It is an account-wide anti-spam restriction, so
            # retrying this recipient (or continuing with the account) only risks
            # extending the restriction.  Remove the account from this worker and
            # let the normal failover/requeue path handle the recipient.
            breaker.record_failure()
            raise _AccountDeadError(
                f"Account peer-flood restricted: {type(exc).__name__}"
            ) from exc

        except (UserDeactivatedBanError, UserDeactivatedError, AuthKeyUnregisteredError) as exc:
            breaker.record_failure()
            raise _AccountDeadError(f"Account dead: {type(exc).__name__}")

        except (
            UserIsBlockedError, InputUserDeactivatedError,
            UserPrivacyRestrictedError, PeerIdInvalidError,
        ) as exc:
            error_name = type(exc).__name__
            logger.info("[%s] Skip @%s: %s", worker_phone, recipient, error_name)
            return SendResult(
                recipient=recipient, worker_phone=worker_phone,
                success=False, error=error_name,
            )

        except Exception as exc:
            # Must resolve the breaker on every failure path -- leaving a HALF_OPEN trial
            # call unresolved sticks _half_open_calls at max and locks out future requests.
            breaker.record_failure()
            logger.error("[%s] Unexpected error → @%s: %s",
                         worker_phone, recipient, exc, exc_info=True)
            return SendResult(
                recipient=recipient, worker_phone=worker_phone,
                success=False, error=f"{type(exc).__name__}: {exc}",
            )

    return SendResult(
        recipient=recipient, worker_phone=worker_phone, success=False,
        error="Max retries reached",
    )


@dataclass
class SendResult:
    recipient: str
    worker_phone: str
    success: bool
    error: Optional[str] = None


@dataclass
class BatchReport:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    errors: Dict[str, str] = field(default_factory=dict)
    per_account: Dict[str, int] = field(default_factory=dict)
    sent_recipients: Set[str] = field(default_factory=set)

    def record(self, result: SendResult) -> None:
        self.total += 1
        if result.success:
            self.succeeded += 1
            self.per_account[result.worker_phone] = (
                self.per_account.get(result.worker_phone, 0) + 1
            )
            self.sent_recipients.add(result.recipient)
        else:
            self.failed += 1
            if result.error:
                self.errors[result.recipient] = result.error

    def merge_from(self, other: "BatchReport") -> None:
        """Folds another (e.g. a later cycle's) report into this one -- used to accumulate totals across exact-total-target cycles or repeat runs."""
        self.total += other.total
        self.succeeded += other.succeeded
        self.failed += other.failed
        self.errors.update(other.errors)
        for phone, count in other.per_account.items():
            self.per_account[phone] = self.per_account.get(phone, 0) + count
        self.sent_recipients |= other.sent_recipients

    @property
    def success_rate(self) -> float:
        return (self.succeeded / self.total * 100) if self.total else 0.0

    def __str__(self) -> str:
        return (
            f"BatchReport["
            f"total={self.total}, "
            f"ok={self.succeeded} ({self.success_rate:.1f}%), "
            f"fail={self.failed}]"
        )


async def _worker(
    client: TelegramClient,
    worker_phone: str,
    task_queue: asyncio.Queue,
    result_queue: asyncio.Queue,
    payload: MessagePayload,
    policy: TimingPolicy,
    rate_limiter: Optional["RedisRateLimiter"],
    coordinator: Optional["FailoverCoordinator"] = None,
    event_bus: Optional[EventBus] = None,
    shutdown_event: Optional[asyncio.Event] = None,
    personalization: Optional[Dict[str, Dict[str, str]]] = None,
    warmup_multipliers: Optional[Dict[str, float]] = None,
    warmup_limiters: Optional[Dict[str, "RedisRateLimiter"]] = None,
    quota: Optional[int] = None,
) -> None:
    """
    On shutdown_event, finishes the in-flight send (not cancelled mid-flight)
    then drains the queue as failures without sending; warmup_limiters
    exhaustion skips (not requeues) this worker's remaining recipients for
    the rest of the run, same as the pool-wide rate_limiter skip below.

    quota, if set, caps how many *successful* sends this worker slot will
    make before it stops pulling more work (its sentinel and any remaining
    recipients are left for other workers, or reported as orphaned by
    send_notifications() if none have capacity left). Recipient-level
    failures (blocked, privacy-restricted, etc.) don't count against the
    quota and don't stop the worker -- it keeps drawing from the shared
    queue, which is what lets it reach at least the caller's configured
    minimum whenever enough recipients exist.
    """
    multiplier = warmup_multipliers.get(worker_phone, 1.0) if warmup_multipliers else 1.0
    adaptive = AdaptiveDelay(policy, warmup_multiplier=multiplier)
    breaker = CircuitBreaker(
        failure_threshold=_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout=_BREAKER_RECOVERY_TIMEOUT,
    )
    sent_count = 0
    logger.info("[%s] Worker started.", worker_phone)

    while True:
        recipient = await task_queue.get()

        if recipient is _SENTINEL:
            task_queue.task_done()
            logger.info("[%s] Sentinel received. Stopping.", worker_phone)
            break

        if shutdown_event is not None and shutdown_event.is_set():
            result = SendResult(
                recipient=recipient, worker_phone=worker_phone,
                success=False, error="shutdown",
            )
            await result_queue.put(result)
            if event_bus is not None:
                await event_bus.publish(MessageDeliveredEvent(
                    worker_phone=worker_phone, recipient=recipient,
                    success=False, error="shutdown",
                ))
            task_queue.task_done()
            continue

        needs_requeue = False
        try:
            warmup_limiter = warmup_limiters.get(worker_phone) if warmup_limiters else None
            if warmup_limiter is not None:
                allowed, _reason = await warmup_limiter.check_and_consume(worker_phone)
                if not allowed:
                    logger.info(
                        "[%s] Skip @%s: warmup_daily_cap_reached", worker_phone, recipient
                    )
                    result = SendResult(
                        recipient=recipient, worker_phone=worker_phone,
                        success=False, error="warmup_daily_cap_reached",
                    )
                    await result_queue.put(result)
                    if event_bus is not None:
                        await event_bus.publish(MessageDeliveredEvent(
                            worker_phone=worker_phone, recipient=recipient,
                            success=False, error="warmup_daily_cap_reached",
                        ))
                    continue

            if rate_limiter is not None:
                allowed, reason = await rate_limiter.check_and_consume(recipient)
                if not allowed:
                    logger.info("[%s] Skip @%s: pool:%s", worker_phone, recipient, reason)
                    result = SendResult(
                        recipient=recipient, worker_phone=worker_phone,
                        success=False, error=f"pool:{reason}",
                    )
                    await result_queue.put(result)
                    if event_bus is not None:
                        await event_bus.publish(MessageDeliveredEvent(
                            worker_phone=worker_phone, recipient=recipient,
                            success=False, error=f"pool:{reason}",
                        ))
                    continue

            result = await _send_rich(
                client, worker_phone, recipient, payload, policy, adaptive, breaker,
                personalization_vars=personalization.get(recipient) if personalization else None,
                shutdown_event=shutdown_event,
            )
            await result_queue.put(result)
            if result.success:
                sent_count += 1
            if event_bus is not None:
                await event_bus.publish(MessageDeliveredEvent(
                    worker_phone=worker_phone,
                    recipient=result.recipient,
                    success=result.success,
                    error=result.error or "",
                ))

        except _AccountDeadError as exc:
            logger.error("[%s] Account dead: %s", worker_phone, exc)

            if event_bus is not None:
                await event_bus.publish(AccountStatusEvent(
                    phone=worker_phone, status="dead", detail=str(exc)
                ))

            if coordinator is not None:
                replacement = await coordinator.get_replacement(worker_phone)
                if replacement is not None:
                    client, worker_phone = replacement
                    # Fresh breaker: the replacement account has no failure history.
                    breaker = CircuitBreaker(
                        failure_threshold=_BREAKER_FAILURE_THRESHOLD,
                        recovery_timeout=_BREAKER_RECOVERY_TIMEOUT,
                    )
                    logger.info("Failover: now running as %s", worker_phone)
                    try:
                        result = await _send_rich(
                            client, worker_phone, recipient, payload, policy, adaptive, breaker,
                            personalization_vars=personalization.get(recipient) if personalization else None,
                        )
                        await result_queue.put(result)
                        if result.success:
                            sent_count += 1
                        if event_bus is not None:
                            await event_bus.publish(MessageDeliveredEvent(
                                worker_phone=worker_phone,
                                recipient=result.recipient,
                                success=result.success,
                                error=result.error or "",
                            ))
                    except _AccountDeadError:
                        fail = SendResult(
                            recipient=recipient, worker_phone=worker_phone,
                            success=False, error="replacement_also_dead",
                        )
                        await result_queue.put(fail)
                        if event_bus is not None:
                            await event_bus.publish(MessageDeliveredEvent(
                                worker_phone=worker_phone, recipient=recipient,
                                success=False, error="replacement_also_dead",
                            ))
                    except Exception as exc2:
                        fail = SendResult(
                            recipient=recipient, worker_phone=worker_phone,
                            success=False, error=str(exc2),
                        )
                        await result_queue.put(fail)
                        if event_bus is not None:
                            await event_bus.publish(MessageDeliveredEvent(
                                worker_phone=worker_phone, recipient=recipient,
                                success=False, error=str(exc2),
                            ))
                    continue
                else:
                    logger.warning("[%s] No spare accounts for failover. Stopping.", worker_phone)
                    needs_requeue = True
            else:
                needs_requeue = True

        except Exception as exc:
            logger.error("[%s] Unhandled exception: %s", worker_phone, exc, exc_info=True)
            fail = SendResult(
                recipient=recipient, worker_phone=worker_phone,
                success=False, error=str(exc),
            )
            await result_queue.put(fail)
            if event_bus is not None:
                await event_bus.publish(MessageDeliveredEvent(
                    worker_phone=worker_phone, recipient=recipient,
                    success=False, error=str(exc),
                ))

        finally:
            if needs_requeue:
                await task_queue.put(recipient)
            task_queue.task_done()

        if needs_requeue:
            break

        if quota is not None and sent_count >= quota:
            logger.info("[%s] Reached per-account quota (%d sent). Stopping.", worker_phone, quota)
            break

        await _interruptible_sleep(adaptive.next_message_delay(), shutdown_event)

    logger.info("[%s] Worker finished.", worker_phone)


async def send_notifications(
    workers: List[Tuple[TelegramClient, str]],
    recipients: Set[str],
    payload: MessagePayload,
    policy: TimingPolicy,
    rate_limiter: Optional["RedisRateLimiter"] = None,
    coordinator: Optional["FailoverCoordinator"] = None,
    event_bus: Optional[EventBus] = None,
    shutdown_event: Optional[asyncio.Event] = None,
    personalization: Optional[Dict[str, Dict[str, str]]] = None,
    warmup_multipliers: Optional[Dict[str, float]] = None,
    warmup_limiters: Optional[Dict[str, "RedisRateLimiter"]] = None,
    messages_per_account_min: int = 1,
    messages_per_account_max: Optional[int] = None,
    worker_batch_size: Optional[int] = None,
    worker_batch_delay_sec: float = 0.0,
) -> BatchReport:
    """
    Distributes recipients across workers via asyncio.Queue; when
    shutdown_event fires, a background watcher injects extra sentinels so
    idle workers wake immediately, while in-flight workers finish their
    current send before draining.

    messages_per_account_max, if set, caps each worker to a random quota in
    [messages_per_account_min, messages_per_account_max] successful sends
    (chosen once per worker here, so it varies per account) -- see
    _worker()'s quota param. None (the default) preserves the original
    unlimited-per-account behavior.

    worker_batch_size, if set, starts workers in groups of that size instead
    of all at once, sleeping worker_batch_delay_sec between groups -- avoids
    every account in the pool beginning to send in the same instant. None
    (the default) starts every worker immediately, as before.
    """
    if not workers:
        logger.error("send_notifications: no workers provided.")
        return BatchReport()
    if not recipients:
        logger.warning("send_notifications: empty recipients list.")
        return BatchReport()

    n_workers = len(workers)
    logger.info("Starting batch: %d recipients → %d workers.", len(recipients), n_workers)

    task_queue: asyncio.Queue = asyncio.Queue()
    result_queue: asyncio.Queue = asyncio.Queue()

    for recipient in recipients:
        await task_queue.put(recipient)

    # Injects extra sentinels on shutdown so workers blocked on task_queue.get() wake
    # immediately.
    shutdown_watcher: Optional[asyncio.Task] = None
    if shutdown_event is not None:
        async def _watch_shutdown() -> None:
            await shutdown_event.wait()
            logger.warning("Shutdown: injecting %d sentinels to unblock workers.", n_workers)
            for _ in range(n_workers):
                task_queue.put_nowait(_SENTINEL)

        shutdown_watcher = asyncio.create_task(_watch_shutdown(), name="shutdown-watcher")

    # Chosen once per worker (not per message) so the quota is a stable
    # per-account trait for this run, matching "N messages from this account".
    per_worker_quota: Optional[Dict[str, int]] = None
    if messages_per_account_max is not None:
        lo = max(0, messages_per_account_min)
        hi = max(lo, messages_per_account_max)
        per_worker_quota = {phone: random.randint(lo, hi) for _, phone in workers}

    batch_size = worker_batch_size if worker_batch_size and worker_batch_size > 0 else n_workers
    worker_tasks: List[asyncio.Task] = []
    for batch_start in range(0, n_workers, batch_size):
        batch = workers[batch_start : batch_start + batch_size]
        worker_tasks.extend(
            asyncio.create_task(
                _worker(
                    client, phone, task_queue, result_queue,
                    payload, policy, rate_limiter, coordinator,
                    event_bus=event_bus,
                    shutdown_event=shutdown_event,
                    personalization=personalization,
                    warmup_multipliers=warmup_multipliers,
                    warmup_limiters=warmup_limiters,
                    quota=per_worker_quota.get(phone) if per_worker_quota else None,
                ),
                name=f"msg-worker-{phone}",
            )
            for client, phone in batch
        )
        if batch_start + batch_size < n_workers:
            await _interruptible_sleep(worker_batch_delay_sec, shutdown_event)

    async def _wait_workers() -> List[object]:
        return await asyncio.gather(*worker_tasks, return_exceptions=True)

    gather_task = asyncio.create_task(_wait_workers(), name="message-workers")
    join_task = asyncio.create_task(task_queue.join(), name="message-queue-join")

    try:
        done, _pending = await asyncio.wait(
            [gather_task, join_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if join_task in done:
            for _ in range(n_workers):
                task_queue.put_nowait(_SENTINEL)
            gather_results = await gather_task
        else:
            gather_results = gather_task.result()
    finally:
        if not join_task.done():
            join_task.cancel()
            try:
                await join_task
            except asyncio.CancelledError:
                pass
        if shutdown_watcher is not None and not shutdown_watcher.done():
            shutdown_watcher.cancel()
            try:
                await shutdown_watcher
            except asyncio.CancelledError:
                pass

    # Drain orphaned items (unprocessed recipients after worker pool exhaustion)
    while not task_queue.empty():
        orphan = task_queue.get_nowait()
        if orphan is not None:
            fail = SendResult(
                recipient=orphan, worker_phone="orphaned",
                success=False, error="no_live_worker",
            )
            await result_queue.put(fail)
            if event_bus is not None:
                await event_bus.publish(MessageDeliveredEvent(
                    worker_phone="orphaned", recipient=orphan,
                    success=False, error="no_live_worker",
                ))
        task_queue.task_done()

    for i, res in enumerate(gather_results):
        if isinstance(res, Exception):
            logger.error("Worker %s crashed: %s", workers[i][1], res, exc_info=res)

    report = BatchReport()
    while not result_queue.empty():
        report.record(result_queue.get_nowait())

    logger.info("Batch complete. %s", report)
    return report
