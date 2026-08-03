"""
tg_pool/features/tdata_convert.py — Standalone tdata -> session batch converter
(MODE=convert_tdata).

Finds every tdata folder under TDATA_ACCOUNTS_DIR (any depth) and converts
each into a Telethon .session file, preserving the original api_id/api_hash/
device fingerprint the auth key was created under -- see TDataConverter's
own docstring for why that matters (mismatched fingerprints on reconnect are
a known ban vector).
"""

from __future__ import annotations

import json
import logging
import os

from tg_pool.proxy.tdata_converter import TDataConverter, find_tdata_folders


async def run(shutdown_event, logger: logging.Logger) -> None:
    tdata_dir = os.getenv("TDATA_ACCOUNTS_DIR", "").strip()
    if not tdata_dir or not os.path.isdir(tdata_dir):
        logger.error("TDATA_ACCOUNTS_DIR не задан или не является директорией.")
        return

    output_dir = os.getenv("TDATA_OUTPUT_DIR", "sessions").strip() or "sessions"
    all_accounts = os.getenv("TDATA_ALL_ACCOUNTS", "0").lower() in ("1", "true", "yes")

    passwords: dict = {}
    passwords_file = os.getenv("TDATA_PASSWORDS_FILE", "").strip()
    if passwords_file and os.path.isfile(passwords_file):
        with open(passwords_file, encoding="utf-8") as fh:
            passwords = json.load(fh)

    tdata_paths = find_tdata_folders(tdata_dir)
    if not tdata_paths:
        logger.warning("Папки tdata не найдены под %s.", tdata_dir)
        return

    logger.info(
        "Конвертация %d папок tdata → %s (all_accounts=%s)…",
        len(tdata_paths), output_dir, all_accounts,
    )

    converter = TDataConverter()
    results = await converter.convert_batch_tdata(
        tdata_paths, output_dir, passwords=passwords, all_accounts=all_accounts,
    )

    for result in results:
        (logger.info if result.success else logger.error)(str(result))

    ok = sum(1 for r in results if r.success)
    logger.info("Готово: %d/%d успешно сконвертировано.", ok, len(results))
