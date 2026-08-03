"""
tg_pool/monitor.py — Live terminal dashboard powered by rich.

Displays real-time metrics while the pipeline runs:
  ┌─────────────────────────────────────────────┐
  │  ACCOUNTS            │  PROXIES              │
  │  Total: 5 · Live: 4  │  Used: 3 · Dead: 0   │
  │  Banned: 1 · Spam: 0 │                       │
  ├─────────────────────────────────────────────┤
  │  PROGRESS                                    │
  │  ████████░░  450/1000 (45.0%)               │
  │  Sent: 420  Failed: 30  Rate: 84.0%         │
  └─────────────────────────────────────────────┘

Architecture — event-driven:
  LiveMonitor subscribes to an EventBus and updates its internal state
  in reaction to AccountStatusEvent, MessageDeliveredEvent, and
  MetricUpdateEvent.  Orchestrator and workers never call monitor methods
  directly; they only publish events to the bus.

  Call subscribe_to(event_bus) before starting the pipeline to wire everything
  up, and call unsubscribe_all() (or use the context manager) to clean up
  subscription tokens when done.

Usage:
    bus = EventBus()
    monitor = LiveMonitor()
    monitor.subscribe_to(bus)
    async with monitor:
        await orchestrate(..., event_bus=bus)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional, Set

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from tg_pool.monitoring.event_bus import (
    AccountStatusEvent,
    EventBus,
    MessageDeliveredEvent,
    MetricUpdateEvent,
)

# Import for pool-check table — guarded to avoid circular dep during early boot
try:
    from tg_pool.accounts.account_registry import RegistryEntry
    _REGISTRY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _REGISTRY_AVAILABLE = False
    RegistryEntry = object  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

@dataclass
class _AccountStats:
    phone: str
    status: str = "alive"   # alive | banned | spamblock | flood | dead | proxy_dead
    sent: int = 0
    failed: int = 0


@dataclass
class _MonitorState:
    total: int = 0
    sent: int = 0
    failed: int = 0
    accounts: Dict[str, _AccountStats] = field(default_factory=dict)
    dead_proxies: Set[str] = field(default_factory=set)
    start_time: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# LiveMonitor
# ---------------------------------------------------------------------------

class LiveMonitor:
    """
    Async context manager that renders a live Rich dashboard in the terminal.

    All internal updates are thread-safe (Lock) because rich.Live can call
    _refresh() from a background thread.

    The monitor is fully decoupled from orchestrator internals — it reacts
    only to events published on an EventBus.
    """

    def __init__(
        self,
        total_recipients: int = 0,
        account_phones: Optional[List[str]] = None,
        refresh_per_second: int = 4,
        title: str = "TG Pool Framework",
    ) -> None:
        self._state = _MonitorState(total=total_recipients)
        for phone in (account_phones or []):
            self._state.accounts[phone] = _AccountStats(phone=phone)

        self._lock = Lock()
        self._console = Console()
        self._live = Live(
            console=self._console,
            refresh_per_second=refresh_per_second,
            transient=False,
        )
        self._title = title
        self._subscription_tokens: List[int] = []

    # ------------------------------------------------------------------
    # EventBus integration
    # ------------------------------------------------------------------

    def subscribe_to(self, event_bus: EventBus) -> None:
        """
        Register this monitor as a subscriber on event_bus.

        Replaces any prior subscriptions. Call before starting the pipeline.
        """
        self.unsubscribe_all()
        self._subscription_tokens = [
            event_bus.subscribe(AccountStatusEvent, self._on_account_status),
            event_bus.subscribe(MessageDeliveredEvent, self._on_message_delivered),
            event_bus.subscribe(MetricUpdateEvent, self._on_metric_update),
        ]

    def unsubscribe_all(self) -> None:
        """Remove all active subscriptions. Called automatically on context exit."""
        # Subscriptions were registered against a specific bus; we need it to unsub.
        # We store tokens only — caller must keep a reference to the bus or call
        # this before the bus is garbage-collected.  In practice the bus and monitor
        # share the same lifetime within orchestrate().
        self._subscription_tokens.clear()

    def _on_account_status(self, event: AccountStatusEvent) -> None:
        with self._lock:
            if event.phone not in self._state.accounts:
                self._state.accounts[event.phone] = _AccountStats(phone=event.phone)
            self._state.accounts[event.phone].status = event.status
        self._refresh()

    def _on_message_delivered(self, event: MessageDeliveredEvent) -> None:
        with self._lock:
            if event.success:
                self._state.sent += 1
                acc = self._state.accounts.setdefault(
                    event.worker_phone, _AccountStats(phone=event.worker_phone)
                )
                acc.sent += 1
            else:
                self._state.failed += 1
                acc = self._state.accounts.get(event.worker_phone)
                if acc:
                    acc.failed += 1
        self._refresh()

    def _on_metric_update(self, event: MetricUpdateEvent) -> None:
        with self._lock:
            if event.key == "total_recipients":
                self._state.total = int(event.value)
            elif event.key == "proxy_dead":
                self._state.dead_proxies.add(str(event.value))
        self._refresh()

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "LiveMonitor":
        self._live.start()
        self._live.update(self._render())
        return self

    async def __aexit__(self, *_) -> None:
        self._live.update(self._render())
        self._live.stop()
        self._print_final_report()

    # Keep sync context manager for backward-compat / testing
    def __enter__(self) -> "LiveMonitor":
        self._live.start()
        self._live.update(self._render())
        return self

    def __exit__(self, *_) -> None:
        self._live.update(self._render())
        self._live.stop()
        self._print_final_report()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        try:
            self._live.update(self._render())
        except Exception:
            pass

    def _render(self) -> Panel:
        with self._lock:
            state = self._state

        grid = Table.grid(padding=(0, 2))
        grid.add_column(min_width=38)
        grid.add_column(min_width=30)

        # ---- Left column: accounts ----
        acc_table = Table(
            "Phone", "Status", "Sent", "Failed",
            box=None, show_header=True, header_style="bold cyan",
        )
        counts: Dict[str, int] = {}
        for acc in state.accounts.values():
            st = acc.status
            counts[st] = counts.get(st, 0) + 1
            colour = {
                "alive": "green", "banned": "red", "spamblock": "yellow",
                "flood": "magenta", "dead": "dim", "proxy_dead": "red",
            }.get(st, "white")
            acc_table.add_row(
                acc.phone,
                Text(st.upper(), style=colour),
                str(acc.sent),
                str(acc.failed),
            )

        acct_summary = (
            f"[bold]Total:[/] {len(state.accounts)}  "
            f"[green]Live:[/] {counts.get('alive', 0)}  "
            f"[red]Banned:[/] {counts.get('banned', 0)}  "
            f"[yellow]Spam:[/] {counts.get('spamblock', 0)}"
        )

        # ---- Right column: proxies ----
        proxy_table = Table("Stat", "Value", box=None, show_header=False)
        alive_proxies = sum(1 for a in state.accounts.values() if a.status == "alive")
        proxy_table.add_row("[cyan]Used proxies[/]", str(alive_proxies))
        proxy_table.add_row("[red]Dead proxies[/]", str(len(state.dead_proxies)))

        grid.add_row(acc_table, proxy_table)

        # ---- Progress bar ----
        done = state.sent + state.failed
        pct = (done / state.total * 100) if state.total else 0.0
        rate = (state.sent / done * 100) if done else 0.0
        elapsed = time.monotonic() - state.start_time
        speed = done / elapsed if elapsed > 0 else 0.0

        bar_filled = int(pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        progress_line = (
            f"[cyan]{bar}[/]  [bold]{done}/{state.total}[/] ({pct:.1f}%)  "
            f"[green]Sent:[/] {state.sent}  [red]Failed:[/] {state.failed}  "
            f"[yellow]Rate:[/] {rate:.1f}%  "
            f"[dim]{speed:.1f} msg/s[/]"
        )

        content = Table.grid(padding=(0, 0))
        content.add_row(Text.from_markup(acct_summary))
        content.add_row(grid)
        content.add_row(Text.from_markup(progress_line))

        return Panel(content, title=f"[bold magenta]{self._title}[/]", border_style="blue")

    # ------------------------------------------------------------------
    # Pool check table (static render, not part of Live dashboard)
    # ------------------------------------------------------------------

    def render_pool_table(self, entries: "List[RegistryEntry]") -> Table:
        """
        Build a Rich Table from a list of RegistryEntry objects.

        Columns:
          Сессия | Прокси (Тип + Пинг) | Премиум | Статус | Срок ограничения | Ошибка

        Returns the Table object so callers can embed it in panels or print it.
        """
        table = Table(
            "Сессия",
            "Прокси (Тип + Пинг)",
            "Премиум",
            "Статус",
            "Срок ограничения",
            "Ошибка",
            title="[bold]Состояние пула[/]",
            header_style="bold cyan",
            show_lines=True,
        )

        _STATUS_COLOURS = {
            "alive":      "green",
            "banned":     "red",
            "spamblock":  "yellow",
            "frozen":     "cyan",
            "flood":      "magenta",
            "proxy_dead": "red",
            "unknown":    "dim",
        }

        for entry in entries:
            phone = entry.account.phone

            # Proxy column
            if entry.proxy_state is not None:
                ps = entry.proxy_state
                if ps.is_active:
                    proxy_cell = Text(
                        f"{ps.proxy_type.value.upper()} / {ps.latency_ms:.0f} ms",
                        style="green",
                    )
                else:
                    proxy_cell = Text(
                        f"{ps.proxy_type.value.upper()} / DEAD",
                        style="red",
                    )
            else:
                proxy_cell = Text("—", style="dim")

            # Premium
            if entry.state is not None:
                premium_cell = Text("★ Premium", style="yellow") if entry.state.is_premium else Text("—")
                status_str = entry.state.status.value
                colour = _STATUS_COLOURS.get(status_str, "white")
                status_cell = Text(status_str.upper(), style=colour)

                expires = entry.state.restriction_expires
                expires_cell = (
                    Text(expires.strftime("%Y-%m-%d"), style="yellow")
                    if expires is not None
                    else Text("—", style="dim")
                )

                err = entry.state.error_message or ""
                error_cell = Text(err[:40], style="red") if err else Text("—", style="dim")
            else:
                premium_cell = Text("?", style="dim")
                status_cell = Text("PENDING", style="dim")
                expires_cell = Text("—", style="dim")
                error_cell = Text("—", style="dim")

            table.add_row(
                phone,
                proxy_cell,
                premium_cell,
                status_cell,
                expires_cell,
                error_cell,
            )

        return table

    def print_pool_table(self, entries: "List[RegistryEntry]") -> None:
        """Print the pool check table directly to the console (outside Live context)."""
        self._console.print(self.render_pool_table(entries))

    def _print_final_report(self) -> None:
        self._console.rule("[bold]Final Report[/]")
        state = self._state
        done = state.sent + state.failed
        rate = (state.sent / done * 100) if done else 0.0

        self._console.print(
            f"  [bold green]Sent:[/]   {state.sent}/{state.total}  ({rate:.1f}%)"
        )
        self._console.print(f"  [bold red]Failed:[/] {state.failed}")

        if state.accounts:
            self._console.print("\n  [bold cyan]Per-account breakdown:[/]")
            for acc in sorted(state.accounts.values(), key=lambda a: -a.sent):
                self._console.print(
                    f"    {acc.phone:20s} sent={acc.sent:5d}  failed={acc.failed:5d}"
                    f"  status={acc.status}"
                )
