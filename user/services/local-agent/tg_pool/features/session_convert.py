"""
tg_pool/features/session_convert.py — Standalone session -> tdata batch converter
(MODE=convert_session).

Finds every .session + .json pair under SESSION_CONVERT_DIR (same pairing
convention as ACCOUNTS_DIR/load_accounts_from_directory -- tg_pool/accounts/
account_loader.py) and converts each to a Telegram Desktop tdata folder,
one subfolder per account named after the session's filename stem.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from tg_pool.proxy.tdata_converter import TDataConverter


async def run(shutdown_event, logger: logging.Logger) -> None:
    session_dir = os.getenv("SESSION_CONVERT_DIR", "").strip()
    if not session_dir or not os.path.isdir(session_dir):
        logger.error("SESSION_CONVERT_DIR не задан или не является директорией.")
        return

    output_base_dir = os.getenv("SESSION_CONVERT_OUTPUT_DIR", "tdata_exports").strip() or "tdata_exports"

    session_configs = []
    for session_file in sorted(Path(session_dir).glob("*.session")):
        json_file = session_file.with_suffix(".json")
        if not json_file.exists():
            logger.warning("Пропущен %s: нет .json пары.", session_file.name)
            continue
        session_configs.append((str(session_file), str(json_file), session_file.stem))

    if not session_configs:
        logger.warning("Пары .session+.json не найдены под %s.", session_dir)
        return

    logger.info("Конвертация %d сессий → %s…", len(session_configs), output_base_dir)

    converter = TDataConverter()
    results = await converter.convert_batch_sessions(session_configs, output_base_dir)

    for result in results:
        (logger.info if result.success else logger.error)(str(result))

    ok = sum(1 for r in results if r.success)
    logger.info("Готово: %d/%d успешно сконвертировано.", ok, len(results))
