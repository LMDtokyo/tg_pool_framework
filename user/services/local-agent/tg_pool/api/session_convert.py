"""
tg_pool/api/session_convert.py — Background session->tdata job lifecycle.

Same shape as TdataConvertManager (tg_pool/api/tdata_convert.py): a single
in-flight run, start()/status(), no stop() -- TDataConverter.convert_batch_sessions()
has no cancellation hook either. `total` is known immediately from the input
list length (mirrors TdataConvertManager's own upfront find_tdata_folders() count).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from tg_pool.proxy.tdata_converter import ConversionResult, TDataConverter

logger = logging.getLogger(__name__)


class SessionConvertAlreadyRunningError(RuntimeError):
    """Raised by SessionConvertManager.start() when a conversion is already in flight."""


@dataclass
class _Run:
    job_id: str
    total: int
    task: Optional[asyncio.Task] = None
    results: List[ConversionResult] = field(default_factory=list)
    finished: bool = False
    error: Optional[str] = None


class SessionConvertManager:
    """Owns at most one in-flight session->tdata conversion at a time."""

    def __init__(self) -> None:
        self._run: Optional[_Run] = None

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def start(
        self,
        session_configs: List[Tuple[str, str, str]],
        output_base_dir: str,
    ) -> str:
        if self.is_running:
            raise SessionConvertAlreadyRunningError("A session conversion is already running.")

        job_id = uuid.uuid4().hex[:12]
        run = _Run(job_id=job_id, total=len(session_configs))

        async def _runner() -> None:
            try:
                run.results = await TDataConverter().convert_batch_sessions(
                    session_configs, output_base_dir,
                )
            except Exception as exc:
                logger.exception("Session conversion %s failed", job_id)
                run.error = str(exc)
            finally:
                run.finished = True

        run.task = asyncio.create_task(_runner(), name=f"api-session-convert-{job_id}")
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
