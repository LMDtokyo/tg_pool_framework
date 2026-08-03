"""Background generator for Telegram Expert ``.session`` + ``.json`` pairs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tg_pool.api.telegram_auth import FingerprintCatalog

logger = logging.getLogger(__name__)


class JsonGeneratorAlreadyRunningError(RuntimeError):
    """Raised when a second generation run is requested."""


@dataclass(frozen=True)
class JsonGeneratorResult:
    time: str
    account: str
    message: str
    success: bool


@dataclass
class _Run:
    job_id: str
    total: int
    task: Optional[asyncio.Task] = None
    results: list[JsonGeneratorResult] = field(default_factory=list)
    finished: bool = False
    cancelled: bool = False
    error: Optional[str] = None


class JsonGeneratorManager:
    """Creates portable JSON sidecars without changing the source sessions."""

    def __init__(self) -> None:
        self._run: Optional[_Run] = None

    @property
    def is_running(self) -> bool:
        return self._run is not None and not self._run.finished

    def start(self, database_path: str, sessions_dir: str, output_dir: str) -> str:
        if self.is_running:
            raise JsonGeneratorAlreadyRunningError("JSON generation is already running.")

        database = Path(database_path)
        source_dir = Path(sessions_dir)
        destination = Path(output_dir)
        if not database.is_file():
            raise ValueError(f"Parameter database not found: {database}")
        if not source_dir.is_dir():
            raise ValueError(f"Session directory not found: {source_dir}")

        # Validate before accepting the job so malformed workbooks are reported immediately.
        catalog = FingerprintCatalog.load(database)
        sessions = sorted(source_dir.rglob("*.session"))
        if not sessions:
            raise ValueError(f"No .session files found under: {source_dir}")
        destination.mkdir(parents=True, exist_ok=True)

        job_id = uuid.uuid4().hex[:12]
        run = _Run(job_id=job_id, total=len(sessions))

        async def _runner() -> None:
            used_signatures: set = set()
            try:
                for session in sessions:
                    await asyncio.sleep(0)
                    fingerprint = catalog.choose(avoid=used_signatures)
                    used_signatures.add(fingerprint.signature())
                    account = session.stem
                    phone = account if account.startswith("+") else f"+{account}"
                    target_session = destination / session.name
                    target_json = destination / f"{session.stem}.json"
                    try:
                        await asyncio.to_thread(shutil.copy2, session, target_session)
                        payload = {
                            "app_id": fingerprint.app_id,
                            "app_hash": fingerprint.app_hash,
                            "phone": phone,
                            "device": fingerprint.device,
                            "system": f"SDK {fingerprint.sdk}",
                            "app_version": fingerprint.app_version,
                            "lang_code": fingerprint.lang_code,
                            "system_lang_code": fingerprint.system_lang_code,
                            "lang_pack": fingerprint.lang_pack,
                            "sdk": fingerprint.sdk,
                            "tz_offset": fingerprint.tz_offset,
                            "perf_cat": fingerprint.perf_cat,
                        }
                        temporary = target_json.with_suffix(f".json.{uuid.uuid4().hex[:8]}.tmp")
                        temporary.write_text(
                            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        os.replace(temporary, target_json)
                        run.results.append(JsonGeneratorResult(
                            time=_timestamp(), account=account,
                            message=f"Created {target_json.name}", success=True,
                        ))
                    except Exception as exc:
                        logger.exception("JSON generation failed for %s", session)
                        run.results.append(JsonGeneratorResult(
                            time=_timestamp(), account=account, message=str(exc), success=False,
                        ))
            except asyncio.CancelledError:
                run.cancelled = True
            except Exception as exc:
                logger.exception("JSON generation %s failed", job_id)
                run.error = str(exc)
            finally:
                run.finished = True

        run.task = asyncio.create_task(_runner(), name=f"api-json-generator-{job_id}")
        self._run = run
        return job_id

    async def stop(self) -> None:
        if self._run is None or self._run.task is None or self._run.finished:
            return
        run = self._run
        run.task.cancel()
        try:
            await run.task
        except asyncio.CancelledError:
            pass
        finally:
            # A task cancelled before its coroutine gets its first execution slice
            # never enters _runner's try/finally block, so finalize it here as well.
            run.cancelled = True
            run.finished = True

    def clear(self) -> None:
        if self.is_running:
            raise JsonGeneratorAlreadyRunningError("Stop JSON generation before clearing its log.")
        self._run = None

    def status(self) -> dict:
        if self._run is None:
            return {"running": False, "results": []}
        return {
            "running": not self._run.finished,
            "job_id": self._run.job_id,
            "total": self._run.total,
            "results": [
                {
                    "time": result.time,
                    "account": result.account,
                    "message": result.message,
                    "success": result.success,
                }
                for result in self._run.results
            ],
            "finished": self._run.finished,
            "cancelled": self._run.cancelled,
            "error": self._run.error,
        }


def _timestamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S")
