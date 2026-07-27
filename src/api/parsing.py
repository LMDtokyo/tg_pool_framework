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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.api.pool_guard import PoolAccessGuard, PoolBusyError
from src.config import AccountConfig, TimingPolicy
from src.extraction.data_extraction import AutoStrategySelector, BaseParsingStrategy
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
    db_path: Optional[str] = None
    report_path: Optional[str] = None
    txt_path: Optional[str] = None
    accounts_used: int = 0
    stats: Optional[Dict[str, int]] = None


def _build_strategy(name: str, topic_id: Optional[int]) -> Optional[BaseParsingStrategy]:
    """Returns None only for name == "auto" -- the caller is expected to pair
    that with an AutoStrategySelector so orchestrate_extraction_only() picks
    a strategy per entity instead of one fixed strategy for the whole job."""
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
    if name == "auto":
        return None
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


def _run_export_dir(export_target: Optional[Path], job_id: str, timestamp: str) -> Path:
    """
    Dedicated per-run subfolder for this job's SQLite/txt/report companion
    files, next to the (often fixed-name, overwritten-every-run) Excel
    export -- keeps a run's own files from mixing with older runs' and with
    each other. The db/txt/report filenames used to all be built from the
    same job_id + an independently-recomputed timestamp; when two of those
    calls landed in the same wall-clock second (i.e. essentially always,
    being sequential lines) they resolved to the exact same path, and
    whichever wrote second silently clobbered the other -- e.g. the report's
    human-readable text overwriting the raw user list that Send by ID reads
    as an audience database. One folder per run with fixed, distinct
    filenames inside it makes that collision structurally impossible.
    """
    base = export_target.parent if export_target is not None else Path("exports")
    run_dir = base / f"parsed_{timestamp}_{job_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _export_sqlite(exporter: DataExporter, run_dir: Path) -> Path:
    """One uniquely-named, never-overwritten SQLite file per run -- so a
    specific past run's results stay findable and reusable by other
    features."""
    return exporter.export_sqlite(run_dir / "database.db")


def _export_txt_list(exporter: DataExporter, run_dir: Path) -> Path:
    """
    Human-readable ("Notepad") download of the collected audience -- for a
    person to read, not to feed to another feature (Send by ID's own "use
    the freshly parsed database" hint points at the Excel export instead,
    which stays fully structured). See DataExporter.export_txt() for the
    sorted/aligned/deduplicated-source formatting.
    """
    return exporter.export_txt(run_dir / "audience.txt")


_REPORT_LABELS: Dict[str, Dict[str, str]] = {
    "ru": {
        "title": "ОТЧЁТ ПАРСИНГА",
        "job_id": "Job ID:",
        "sources": "Источники:",
        "strategy": "Стратегия:",
        "accounts_used": "Задействовано аккаунтов:",
        "collected": "Собрано пользователей:",
        "with_username": "  С юзернеймом:",
        "without_username": "  Без юзернейма:",
        "with_phone": "  С номером телефона:",
        "premium": "  Premium:",
        "bots": "  Ботов:",
        "excel": "Excel:",
        "sqlite": "SQLite:",
        "txt": "Блокнот:",
    },
    "en": {
        "title": "PARSING REPORT",
        "job_id": "Job ID:",
        "sources": "Sources:",
        "strategy": "Strategy:",
        "accounts_used": "Accounts used:",
        "collected": "Users collected:",
        "with_username": "  With username:",
        "without_username": "  Without username:",
        "with_phone": "  With phone number:",
        "premium": "  Premium:",
        "bots": "  Bots:",
        "excel": "Excel:",
        "sqlite": "SQLite:",
        "txt": "Notepad:",
    },
    "zh": {
        "title": "解析报告",
        "job_id": "任务 ID：",
        "sources": "来源：",
        "strategy": "策略：",
        "accounts_used": "使用的账户数：",
        "collected": "采集用户数：",
        "with_username": "  有用户名：",
        "without_username": "  无用户名：",
        "with_phone": "  有电话号码：",
        "premium": "  Premium：",
        "bots": "  机器人：",
        "excel": "Excel：",
        "sqlite": "SQLite：",
        "txt": "记事本：",
    },
}


def _write_report(run: "_Run", strategy_name: str, run_dir: Path, language: str = "ru") -> Path:
    """Human-readable summary written alongside the per-run exports -- the
    WPF launcher opens this in a console window once the job finishes, and
    the same numbers are shown in-app via ParsingManager.status(). `language`
    mirrors the WPF app's currently selected UI language (ru/en/zh, see
    LocalizationService.CurrentLanguage), so the console the launcher pops
    open reads in whatever language the rest of the app is already in."""
    labels = _REPORT_LABELS.get(language, _REPORT_LABELS["ru"])
    width = max(len(value) for key, value in labels.items() if key != "title")

    def line(key: str, value: object) -> str:
        return f"{labels[key].ljust(width)} {value}"

    stats = run.stats or {}
    lines = [
        "=" * 50,
        labels["title"],
        "=" * 50,
        line("job_id", run.job_id),
        line("sources", ", ".join(run.entities)),
        line("strategy", strategy_name),
        line("accounts_used", run.accounts_used),
        "",
        line("collected", stats.get("total", 0)),
        line("with_username", stats.get("with_username", 0)),
        line("without_username", stats.get("without_username", 0)),
        line("with_phone", stats.get("with_phone", 0)),
        line("premium", stats.get("premium", 0)),
        line("bots", stats.get("bots", 0)),
        "",
        line("excel", run.export_path or "-"),
        line("sqlite", run.db_path or "-"),
        line("txt", run.txt_path or "-"),
        "=" * 50,
    ]

    report_path = run_dir / "report.txt"
    # utf-16 (with BOM) rather than utf-8: Windows' classic console (cmd.exe's
    # `type`) reads UTF-16-with-BOM natively via its wide-char path, but
    # garbles multi-byte UTF-8 sequences through its legacy OEM-codepage byte
    # translation even after `chcp 65001` -- ASCII survives either way, which
    # is why only the Cyrillic came out as mojibake.
    report_path.write_text("\n".join(lines), encoding="utf-16")
    return report_path


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
        language: str = "ru",
    ) -> str:
        """Launches orchestrate_extraction_only() as a background task. Returns job_id."""
        if self.is_running:
            raise ParsingAlreadyRunningError("A parsing job is already running.")
        try:
            self._pool_guard.try_acquire("parsing")
        except PoolBusyError as exc:
            raise ParsingAlreadyRunningError(str(exc)) from exc

        strategy = _build_strategy(strategy_name, topic_id)
        strategy_selector = AutoStrategySelector() if strategy is None else None
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
                    strategy_selector=strategy_selector,
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
                run.accounts_used = len(tracker.snapshot.worker_statuses)
                run.stats = exporter.stats()
                export_target = _export(exporter, export_mode, export_path)
                run.export_path = str(export_target)
                run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                run_dir = _run_export_dir(export_target, job_id, run_timestamp)
                run.db_path = str(_export_sqlite(exporter, run_dir))
                run.txt_path = str(_export_txt_list(exporter, run_dir))
                run.report_path = str(_write_report(run, strategy_name, run_dir, language))
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

    async def list_sources(self, limit: int = 200) -> List[dict]:
        """
        Briefly borrows the first pool account to list its joined
        chats/channels/groups, for the UI's source picker (browse instead of
        typing raw links/usernames). Uses its own pool_guard holder name
        (distinct from start()'s "parsing") so PoolAccessGuard -- which only
        conflicts on a *different* holder, same holder is a no-op re-acquire
        -- actually treats a running parsing job as a conflict instead of
        silently letting this reuse its reservation.
        """
        if not self._accounts:
            return []
        try:
            self._pool_guard.try_acquire("parsing_sources")
        except PoolBusyError as exc:
            raise ParsingAlreadyRunningError(str(exc)) from exc

        from telethon.tl.types import Channel, Chat

        from src.accounts.connection_manager import ClientFactory

        client = ClientFactory.build(self._accounts[0])
        try:
            await client.connect()
            if not await client.is_user_authorized():
                logger.warning("list_sources: %s is not authorized.", self._accounts[0].phone)
                return []

            sources: List[dict] = []
            async for dialog in client.iter_dialogs(limit=limit):
                entity = dialog.entity
                if isinstance(entity, Channel):
                    kind = "supergroup" if entity.megagroup else "channel"
                elif isinstance(entity, Chat):
                    kind = "chat"
                else:
                    continue  # private 1:1 dialogs (users/bots) aren't parsing targets

                username = getattr(entity, "username", None)
                identifier = f"@{username}" if username else str(entity.id)
                sources.append({
                    "identifier": identifier,
                    "title": dialog.title or identifier,
                    "kind": kind,
                    "members_count": getattr(entity, "participants_count", None),
                })
            return sources
        finally:
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                logger.warning("list_sources: failed to disconnect cleanly.", exc_info=True)
            self._pool_guard.release("parsing_sources")

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
            "db_path": self._run.db_path,
            "report_path": self._run.report_path,
            "txt_path": self._run.txt_path,
            "accounts_used": self._run.accounts_used,
            "stats": self._run.stats,
            "finished": self._run.finished,
            "error": self._run.error,
        }
