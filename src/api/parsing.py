"""
src/api/parsing.py — Single-parsing-job task lifecycle + headless progress tracking.

Keeps the task handle,
set shutdown_event to stop (never cancel() it -- that would skip
orchestrator.py's Phase 4 cleanup), await the task to know it's actually
finished. Uses PoolAccessGuard (src/api/pool_guard.py) to reserve the
account pool while parsing is active.

ParsingProgressTracker listens to the parsing pipeline's own events:
AccountStatusEvent (worker pool status) and
MetricUpdateEvent(key="total_recipients", ...) (users collected so far) --
orchestrate_extraction_only() (src/orchestrator.py) publishes both when
given an event_bus.

Unlike the CLI's src/features/parsing.py (which reads PARSE_* env vars),
strategy/filters/entities all come from explicit request fields.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from src.api.pool_guard import PoolAccessGuard, PoolBusyError
from src.config import AccountConfig, TimingPolicy
from src.extraction.data_extraction import BaseParsingStrategy
from src.extraction.exporter import DataExporter
from src.extraction.user_filter import UserFilterPipeline
from src.monitoring.event_bus import AccountStatusEvent, EventBus, MetricUpdateEvent
from src.orchestrator import orchestrate_extraction_only

logger = logging.getLogger(__name__)


class ParsingAlreadyRunningError(RuntimeError):
    """Raised by ParsingManager.start() when a parsing job is already in flight."""


@dataclass
class _ProgressState:
    total_collected: int = 0
    worker_statuses: Dict[str, str] = field(default_factory=dict)


class ParsingProgressTracker:
    """Headless progress tracker for one parsing job."""

    def __init__(self) -> None:
        self._state = _ProgressState()
        self._event_bus: Optional[EventBus] = None
        self._tokens: List[int] = []

    def subscribe_to(self, event_bus: EventBus) -> None:
        self.unsubscribe_all()
        self._event_bus = event_bus
        self._tokens = [
            event_bus.subscribe(AccountStatusEvent, self._on_account_status),
            event_bus.subscribe(MetricUpdateEvent, self._on_metric_update),
        ]

    def unsubscribe_all(self) -> None:
        if self._event_bus is not None:
            for token in self._tokens:
                self._event_bus.unsubscribe(token)
        self._tokens.clear()
        self._event_bus = None

    def _on_account_status(self, event: AccountStatusEvent) -> None:
        self._state.worker_statuses[event.phone] = event.status

    def _on_metric_update(self, event: MetricUpdateEvent) -> None:
        if event.key == "total_recipients":
            self._state.total_collected = int(event.value)

    @property
    def snapshot(self) -> _ProgressState:
        return self._state


@dataclass
class _Run:
    job_id: str
    entities: List[str]
    shutdown_event: asyncio.Event
    tracker: ParsingProgressTracker
    task: Optional[asyncio.Task] = None
    finished: bool = False
    error: Optional[str] = None
    sources: List[str] = field(default_factory=list)
    export_path: Optional[str] = None


def _build_strategy(name: str, topic_id: Optional[int]) -> BaseParsingStrategy:
    from src.extraction.data_extraction import (
        ChannelCommentsStrategy,
        GroupMembersStrategy,
        GroupMessagesStrategy,
        PollsStrategy,
        ReactionsStrategy,
        SystemMessagesStrategy,
        TopicMessagesStrategy,
    )
    strategies = {
        "members": GroupMembersStrategy,
        "comments": ChannelCommentsStrategy,
        "messages": GroupMessagesStrategy,
        "reactions": ReactionsStrategy,
        "polls": PollsStrategy,
        "system": SystemMessagesStrategy,
    }
    if name == "topic":
        if not topic_id:
            raise ValueError("strategy='topic' requires topic_id.")
        return TopicMessagesStrategy(topic_id=topic_id)
    if name not in strategies:
        raise ValueError(f"Unknown strategy {name!r}")
    return strategies[name]()


def _build_user_filter(filters: Dict[str, object]) -> UserFilterPipeline:
    from src.extraction.user_filter import (
        GenderFilter,
        HasAvatarFilter,
        IsBotFilter,
        IsPremiumFilter,
        LastSeenFilter,
    )
    chain = []
    if filters.get("last_seen_days"):
        chain.append(LastSeenFilter(days=int(filters["last_seen_days"])))
    if filters.get("gender"):
        chain.append(GenderFilter(str(filters["gender"])))
    if filters.get("has_avatar"):
        chain.append(HasAvatarFilter())
    if filters.get("premium"):
        chain.append(IsPremiumFilter())
    if filters.get("exclude_bots", True):
        chain.append(IsBotFilter(is_bot=False))
    return UserFilterPipeline(chain)


def _single_file_export_path(export_path: Optional[str], default_name: str) -> Path:
    """Resolve a full/summary export target from a file or directory path."""
    path = Path(export_path) if export_path else Path("exports") / default_name
    if path.is_dir() or not path.suffix:
        path /= default_name
    return path


def _export(exporter: DataExporter, mode: str, export_path: Optional[str]) -> Path:
    if mode == "summary":
        path = _single_file_export_path(export_path, "parsed_summary.xlsx")
        exporter.export_summary(path)
    elif mode == "by_source":
        path = Path(export_path or "exports/by_source")
        exporter.export_by_source(path)
    else:
        path = _single_file_export_path(export_path, "parsed_full.xlsx")
        exporter.export_full(path)
    return path


class ParsingManager:
    """Owns at most one in-flight parsing job at a time."""

    def __init__(
        self,
        event_bus: EventBus,
        accounts: List[AccountConfig],
        spare_accounts: Optional[List[AccountConfig]],
        policy: TimingPolicy,
        session_encryption_key: Optional[bytes],
        pool_guard: PoolAccessGuard,
    ) -> None:
        self._event_bus = event_bus
        self._accounts = accounts
        self._spare_accounts = spare_accounts
        self._policy = policy
        self._session_encryption_key = session_encryption_key
        self._pool_guard = pool_guard
        self._run: Optional[_Run] = None

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def start(
        self,
        entities: List[str],
        strategy_name: str,
        topic_id: Optional[int],
        filters: Dict[str, object],
        export_mode: str,
        export_path: Optional[str],
        redis_dedup_enabled: bool = False,
        job_key: Optional[str] = None,
    ) -> str:
        """Launches orchestrate_extraction_only() as a background task. Returns job_id."""
        if self.is_running:
            raise ParsingAlreadyRunningError("A parsing job is already running.")
        try:
            self._pool_guard.try_acquire("parsing")
        except PoolBusyError as exc:
            raise ParsingAlreadyRunningError(str(exc)) from exc

        strategy = _build_strategy(strategy_name, topic_id)
        user_filter = _build_user_filter(filters)

        job_id = uuid.uuid4().hex[:12]
        shutdown_event = asyncio.Event()
        tracker = ParsingProgressTracker()
        tracker.subscribe_to(self._event_bus)

        run = _Run(job_id=job_id, entities=entities, shutdown_event=shutdown_event, tracker=tracker)

        async def _runner() -> None:
            import src.bootstrap as bootstrap
            redis_client = bootstrap.build_redis_client() if redis_dedup_enabled else None
            try:
                exporter = await orchestrate_extraction_only(
                    accounts=self._accounts,
                    entity_identifiers=entities,
                    strategy=strategy,
                    user_filter=user_filter,
                    policy=self._policy,
                    spare_accounts=self._spare_accounts or None,
                    event_bus=self._event_bus,
                    shutdown_event=shutdown_event,
                    session_encryption_key=self._session_encryption_key,
                    redis_client=redis_client,
                    job_key=job_key,
                )
                run.sources = list(exporter.sources)
                run.export_path = str(_export(exporter, export_mode, export_path))
            except Exception as exc:
                logger.exception("Parsing job %s failed", job_id)
                run.error = str(exc)
            finally:
                if redis_client is not None:
                    try:
                        await redis_client.aclose()
                    except Exception:
                        logger.warning("Failed to close Redis client cleanly.", exc_info=True)
                tracker.unsubscribe_all()
                run.finished = True
                self._pool_guard.release("parsing")

        run.task = asyncio.create_task(_runner(), name=f"api-parsing-{job_id}")
        self._run = run
        return job_id

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
            "job_id": self._run.job_id,
            "entities": self._run.entities,
            "total_collected": snap.total_collected,
            "sources": self._run.sources,
            "export_path": self._run.export_path,
            "finished": self._run.finished,
            "error": self._run.error,
        }
