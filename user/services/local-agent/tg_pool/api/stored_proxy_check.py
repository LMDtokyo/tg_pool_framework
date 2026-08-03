"""Background checking for proxies loaded from and written back to the database."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from tg_pool.db.proxy_repository import ProxyRepository
from tg_pool.proxy.proxy_checker import ProxyState, check_all_proxies


logger = logging.getLogger(__name__)


class StoredProxyCheckAlreadyRunningError(RuntimeError):
    pass


@dataclass
class _StoredRun:
    job_id: str
    proxy_ids: Optional[List[int]]
    task: Optional[asyncio.Task] = None
    total: int = 0
    results: List[ProxyState] = field(default_factory=list)
    finished: bool = False
    error: Optional[str] = None


class StoredProxyCheckManager:
    def __init__(self, repository: ProxyRepository) -> None:
        self._repository = repository
        self._run: Optional[_StoredRun] = None

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def start(
        self,
        proxy_ids: Optional[Sequence[int]],
        *,
        concurrency: int,
        timeout: float,
        retries: int,
        retry_delay: float,
    ) -> str:
        if self.is_running:
            raise StoredProxyCheckAlreadyRunningError("A stored proxy check is already running.")

        run = _StoredRun(
            job_id=str(uuid.uuid4()),
            proxy_ids=list(dict.fromkeys(proxy_ids)) if proxy_ids is not None else None,
        )
        self._run = run
        run.task = asyncio.create_task(
            self._execute(run, concurrency, timeout, retries, retry_delay)
        )
        return run.job_id

    async def _execute(
        self,
        run: _StoredRun,
        concurrency: int,
        timeout: float,
        retries: int,
        retry_delay: float,
    ) -> None:
        try:
            proxies = await self._repository.list_for_check(run.proxy_ids)
            run.total = len(proxies)
            if not proxies:
                raise ValueError("No stored proxies matched the request.")
            configs = [proxy.checker_config(timeout) for proxy in proxies]
            run.results = await check_all_proxies(
                configs,
                concurrency=concurrency,
                retries=retries,
                retry_delay=retry_delay,
            )
            await self._repository.update_results(proxies, run.results)
        except Exception as exc:
            logger.exception("Stored proxy check failed")
            run.error = str(exc)
        finally:
            run.finished = True

    def status(self) -> dict:
        run = self._run
        if run is None:
            return {
                "running": False,
                "job_id": None,
                "total": 0,
                "completed": 0,
                "finished": False,
                "error": None,
            }
        return {
            "running": not run.finished,
            "job_id": run.job_id,
            "total": run.total,
            "completed": len(run.results),
            "finished": run.finished,
            "error": run.error,
        }

    async def stop(self) -> None:
        if self._run is None or self._run.task is None or self._run.task.done():
            return
        self._run.task.cancel()
        try:
            await self._run.task
        except asyncio.CancelledError:
            pass
