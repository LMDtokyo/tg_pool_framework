"""
tg_pool/api/proxy_check.py — Background proxy-check job lifecycle.

Same one-in-flight-run shape as the other API job managers,
a _Run dataclass holding the task/results, status() as a plain dict. Simpler
than parsing though -- check_all_proxies() (tg_pool/proxy/
proxy_checker.py) has no shutdown_event/event_bus hook, so there's no stop()
and no live progress tracker, only start()/status().
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tg_pool.proxy.proxy_checker import ProxyState, check_all_proxies

logger = logging.getLogger(__name__)


class ProxyCheckAlreadyRunningError(RuntimeError):
    """Raised by ProxyCheckManager.start() when a check is already in flight."""


@dataclass
class _Run:
    job_id: str
    proxies: List[Dict[str, Any]]
    task: Optional[asyncio.Task] = None
    results: List[ProxyState] = field(default_factory=list)
    finished: bool = False
    error: Optional[str] = None


class ProxyCheckManager:
    """Owns at most one in-flight proxy check at a time."""

    def __init__(self) -> None:
        self._run: Optional[_Run] = None

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def start(self, proxies: List[Dict[str, Any]], concurrency: int) -> str:
        if self.is_running:
            raise ProxyCheckAlreadyRunningError("A proxy check is already running.")

        job_id = uuid.uuid4().hex[:12]
        run = _Run(job_id=job_id, proxies=proxies)

        async def _runner() -> None:
            try:
                run.results = await check_all_proxies(proxies, concurrency=concurrency)
            except Exception as exc:
                logger.exception("Proxy check %s failed", job_id)
                run.error = str(exc)
            finally:
                run.finished = True

        run.task = asyncio.create_task(_runner(), name=f"api-proxy-check-{job_id}")
        self._run = run
        return job_id

    def status(self) -> dict:
        if self._run is None:
            return {"running": False}
        return {
            "running": not self._run.finished,
            "job_id": self._run.job_id,
            "total": len(self._run.proxies),
            "results": [
                {
                    "host": proxy.get("host", ""),
                    "port": proxy.get("port", 0),
                    "proxy_type": state.proxy_type.value,
                    "is_active": state.is_active,
                    "latency_ms": state.latency_ms,
                    "error_message": state.error_message,
                    "country": state.country,
                }
                for proxy, state in zip(self._run.proxies, self._run.results)
            ],
            "finished": self._run.finished,
            "error": self._run.error,
        }
