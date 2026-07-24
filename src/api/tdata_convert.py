"""
src/api/tdata_convert.py — Background tdata-conversion job lifecycle.

Same shape as ProxyCheckManager (src/api/proxy_check.py): a single in-flight
run, start()/status(), no stop() -- TDataConverter.convert_batch_tdata() has
no shutdown_event/cancellation hook either.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.proxy.tdata_converter import ConversionResult, TDataConverter, find_tdata_folders

logger = logging.getLogger(__name__)


class TdataConvertAlreadyRunningError(RuntimeError):
    """Raised by TdataConvertManager.start() when a conversion is already in flight."""


@dataclass
class _Run:
    job_id: str
    tdata_dir: str
    total: int
    task: Optional[asyncio.Task] = None
    results: List[ConversionResult] = field(default_factory=list)
    finished: bool = False
    error: Optional[str] = None


class TdataConvertManager:
    """Owns at most one in-flight tdata conversion at a time."""

    def __init__(self) -> None:
        self._run: Optional[_Run] = None

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def start(
        self,
        tdata_dir: str,
        output_dir: str,
        all_accounts: bool,
        passwords: Optional[Dict[str, str]],
    ) -> str:
        if self.is_running:
            raise TdataConvertAlreadyRunningError("A tdata conversion is already running.")
        if not os.path.isdir(tdata_dir):
            raise ValueError(f"Not a directory: {tdata_dir}")

        tdata_paths = find_tdata_folders(tdata_dir)
        if not tdata_paths:
            raise ValueError(f"No valid tdata folders found under: {tdata_dir}")
        job_id = uuid.uuid4().hex[:12]
        run = _Run(job_id=job_id, tdata_dir=tdata_dir, total=len(tdata_paths))

        async def _runner() -> None:
            try:
                run.results = await TDataConverter().convert_batch_tdata(
                    tdata_paths, output_dir, passwords=passwords, all_accounts=all_accounts,
                )
            except Exception as exc:
                logger.exception("Tdata conversion %s failed", job_id)
                run.error = str(exc)
            finally:
                run.finished = True

        run.task = asyncio.create_task(_runner(), name=f"api-tdata-convert-{job_id}")
        self._run = run
        return job_id

    def status(self) -> dict:
        if self._run is None:
            return {"running": False}
        return {
            "running": not self._run.finished,
            "job_id": self._run.job_id,
            "total": self._run.total,
            "results": [
                {
                    "source": r.source,
                    "output": r.output,
                    "success": r.success,
                    "error": r.error,
                }
                for r in self._run.results
            ],
            "finished": self._run.finished,
            "error": self._run.error,
        }
