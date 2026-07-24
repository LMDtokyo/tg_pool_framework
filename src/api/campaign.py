from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.accounts.account_registry import AccountRegistry
from src.api.pool_guard import PoolAccessGuard, PoolBusyError
from src.config import AccountConfig, TimingPolicy
from src.messaging.messaging_service import BatchReport, MessagePayload
from src.monitoring.event_bus import EventBus, MessageDeliveredEvent, MetricUpdateEvent
from src.orchestrator import orchestrate_multi_source, orchestrate_until_target, run_with_repeat

logger = logging.getLogger(__name__)


class CampaignAlreadyRunningError(RuntimeError):
    pass


@dataclass
class _ProgressState:
    total: int = 0
    sent: int = 0
    failed: int = 0
    per_account: Dict[str, int] = field(default_factory=dict)


class CampaignProgressTracker:
    """Headless sibling of LiveMonitor's _MonitorState -- no rich.Live coupling."""

    def __init__(self) -> None:
        self._state = _ProgressState()
        self._event_bus: Optional[EventBus] = None
        self._tokens: List[int] = []

    def subscribe_to(self, event_bus: EventBus) -> None:
        self.unsubscribe_all()
        self._event_bus = event_bus
        self._tokens = [
            event_bus.subscribe(MessageDeliveredEvent, self._on_message_delivered),
            event_bus.subscribe(MetricUpdateEvent, self._on_metric_update),
        ]

    def unsubscribe_all(self) -> None:
        if self._event_bus is not None:
            for token in self._tokens:
                self._event_bus.unsubscribe(token)
        self._tokens.clear()
        self._event_bus = None

    def _on_message_delivered(self, event: MessageDeliveredEvent) -> None:
        if event.success:
            self._state.sent += 1
            self._state.per_account[event.worker_phone] = (
                self._state.per_account.get(event.worker_phone, 0) + 1
            )
        else:
            self._state.failed += 1

    def _on_metric_update(self, event: MetricUpdateEvent) -> None:
        if event.key == "total_recipients":
            self._state.total = int(event.value)

    @property
    def snapshot(self) -> _ProgressState:
        return self._state


@dataclass
class _Run:
    campaign_id: str
    target: str
    shutdown_event: asyncio.Event
    tracker: CampaignProgressTracker
    task: Optional[asyncio.Task] = None
    finished: bool = False
    error: Optional[str] = None
    report: Optional[BatchReport] = None


class CampaignManager:
    """Owns at most one in-flight campaign at a time."""

    def __init__(
        self,
        event_bus: EventBus,
        registry: AccountRegistry,
        accounts: List[AccountConfig],
        spare_accounts: Optional[List[AccountConfig]],
        policy: TimingPolicy,
        session_encryption_key: Optional[bytes],
        pool_guard: PoolAccessGuard,
    ) -> None:
        self._event_bus = event_bus
        self._registry = registry
        self._accounts = accounts
        self._spare_accounts = spare_accounts
        self._policy = policy
        self._session_encryption_key = session_encryption_key
        self._pool_guard = pool_guard
        self._run: Optional[_Run] = None

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def _filter_by_folder(self, accounts: List[AccountConfig], folder: str) -> List[AccountConfig]:
        return [
            a for a in accounts
            if (entry := self._registry.get(a.phone)) is not None and entry.folder == folder
        ]

    def start(
        self,
        target: str,
        payload: MessagePayload,
        account_folder: Optional[str] = None,
        messages_per_account_min: int = 1,
        messages_per_account_max: Optional[int] = None,
        exact_total_target: Optional[int] = None,
        worker_batch_size: Optional[int] = None,
        worker_batch_delay_sec: float = 0.0,
        repeat_every_hours: Optional[float] = None,
    ) -> str:
        """Launches orchestrate_multi_source() as a background task. Returns campaign_id."""
        if self.is_running:
            raise CampaignAlreadyRunningError("A campaign is already running.")

        accounts = self._accounts
        spare_accounts = self._spare_accounts
        if account_folder:
            accounts = self._filter_by_folder(accounts, account_folder)
            if spare_accounts:
                spare_accounts = self._filter_by_folder(spare_accounts, account_folder)
            if not accounts:
                raise ValueError(f"No accounts found in folder {account_folder!r}.")

        try:
            self._pool_guard.try_acquire("campaign")
        except PoolBusyError as exc:
            raise CampaignAlreadyRunningError(str(exc)) from exc

        campaign_id = uuid.uuid4().hex[:12]
        shutdown_event = asyncio.Event()
        tracker = CampaignProgressTracker()
        tracker.subscribe_to(self._event_bus)

        run = _Run(
            campaign_id=campaign_id,
            target=target,
            shutdown_event=shutdown_event,
            tracker=tracker,
        )

        async def _run_once() -> BatchReport:
            common_kwargs = dict(
                accounts=accounts,
                entity_identifiers=[target],
                payload=payload,
                policy=self._policy,
                spare_accounts=spare_accounts or None,
                event_bus=self._event_bus,
                shutdown_event=shutdown_event,
                session_encryption_key=self._session_encryption_key,
                registry=self._registry,
                messages_per_account_min=messages_per_account_min,
                messages_per_account_max=messages_per_account_max,
                worker_batch_size=worker_batch_size,
                worker_batch_delay_sec=worker_batch_delay_sec,
            )
            if exact_total_target is not None:
                return await orchestrate_until_target(exact_total_target=exact_total_target, **common_kwargs)
            return await orchestrate_multi_source(**common_kwargs)

        async def _runner() -> None:
            try:
                run.report = await run_with_repeat(_run_once, shutdown_event, repeat_every_hours)
            except Exception as exc:
                logger.exception("Campaign %s failed", campaign_id)
                run.error = str(exc)
            finally:
                tracker.unsubscribe_all()
                run.finished = True
                self._pool_guard.release("campaign")

        run.task = asyncio.create_task(_runner(), name=f"api-campaign-{campaign_id}")
        self._run = run
        return campaign_id

    async def stop(self) -> None:
        """Requests graceful shutdown and awaits Phase 4 cleanup -- never cancels the task."""
        if self._run is None or self._run.task is None:
            return
        self._run.shutdown_event.set()
        await self._run.task

    def status(self) -> dict:
        if self._run is None:
            return {"running": False}
        snap = self._run.tracker.snapshot
        return {
            "running": not self._run.finished,
            "campaign_id": self._run.campaign_id,
            "target": self._run.target,
            "total": snap.total,
            "sent": snap.sent,
            "failed": snap.failed,
            "per_account": dict(snap.per_account),
            "finished": self._run.finished,
            "error": self._run.error,
        }
