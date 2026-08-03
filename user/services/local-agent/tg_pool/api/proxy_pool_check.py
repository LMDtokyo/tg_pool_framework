"""Background proxy-pool exit-IP check job lifecycle."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from tg_pool.proxy.proxy_pool_checker import ProxyPoolReport, check_proxy_pool

logger = logging.getLogger(__name__)


class ProxyPoolCheckAlreadyRunningError(RuntimeError):
    """Raised when a proxy-pool check is already in flight."""


@dataclass
class _Run:
    job_id: str
    mode: str
    proxies: List[Dict[str, Any]]
    request_count: Optional[int]
    task: Optional[asyncio.Task] = None
    report: Optional[ProxyPoolReport] = None
    finished: bool = False
    error: Optional[str] = None


class ProxyPoolCheckManager:
    """Owns at most one in-flight proxy-pool check."""

    def __init__(self) -> None:
        self._run: Optional[_Run] = None

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def start(
        self,
        *,
        mode: str,
        proxies: List[Dict[str, Any]],
        request_count: Optional[int],
        concurrency: int,
    ) -> str:
        if self.is_running:
            raise ProxyPoolCheckAlreadyRunningError("A proxy pool check is already running.")

        job_id = uuid.uuid4().hex[:12]
        run = _Run(job_id=job_id, mode=mode, proxies=proxies, request_count=request_count)

        async def _runner() -> None:
            try:
                run.report = await check_proxy_pool(
                    proxies,
                    mode=mode,
                    request_count=request_count,
                    concurrency=concurrency,
                )
            except Exception as exc:
                logger.exception("Proxy pool check %s failed", job_id)
                run.error = str(exc)
            finally:
                run.finished = True

        run.task = asyncio.create_task(_runner(), name=f"api-proxy-pool-check-{job_id}")
        self._run = run
        return job_id

    def status(self) -> dict:
        if self._run is None:
            return {"running": False}

        report = self._run.report
        return {
            "running": not self._run.finished,
            "job_id": self._run.job_id,
            "mode": self._run.mode,
            "total": report.total if report else (
                self._run.request_count if self._run.mode == "rotating" else len(self._run.proxies)
            ) or 0,
            "unique": report.unique_count if report else 0,
            "duplicates": report.duplicate_count if report else 0,
            "connection_errors": report.error_count if report else 0,
            "finished": self._run.finished,
            "error": self._run.error,
        }
