"""
main.py — Точка входа фреймворка tg_pool_framework.

Порядок запуска:
    cp .env.example .env
    # заполните .env, включая MODE (или оставьте пустым для интерактивного меню)
    python main.py

Режимы (MODE=...), каждый — независимая фича со своими настройками в .env:
    send            — рассылка сообщений (кампания)
    parse           — сбор пользователей (парсинг)
    check_accounts  — проверка здоровья аккаунтов
    check_proxies   — проверка прокси
    convert_tdata   — конвертация tdata → session
    convert_session — конвертация session → tdata

Если MODE не задан и запуск интерактивный (TTY) — показывается меню выбора
(заготовка под будущий графический UI, который будет вызывать те же модули
src.features.* напрямую, без этого меню). Без TTY и без MODE — понятная
ошибка вместо зависания на вводе (Docker/cron-дружелюбно).

Graceful shutdown:
    Ctrl+C (SIGINT) или SIGTERM (Linux/macOS) — активный режим завершает
    текущую итерацию сетевого запроса и дренирует очередь перед выходом.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import src.bootstrap as bootstrap

_MODES = {
    "send": ("Рассылка сообщений", "src.features.messaging"),
    "parse": ("Сбор пользователей (парсинг)", "src.features.parsing"),
    "check_accounts": ("Проверка аккаунтов", "src.features.account_check"),
    "check_proxies": ("Проверка прокси", "src.features.proxy_check"),
    "convert_tdata": ("Конвертация tdata в session", "src.features.tdata_convert"),
    "convert_session": ("Конвертация session в tdata", "src.features.session_convert"),
}


def choose_mode(logger: logging.Logger) -> Optional[str]:
    """
    Resolves which mode to run: the MODE env var if set, otherwise an
    interactive console menu (TTY only) -- a stand-in for the future UI,
    which will call the feature modules directly instead of going through
    this prompt.

    Returns None (caller should abort) if MODE is unset and there's no TTY
    to prompt on -- e.g. a cron/Docker run without MODE set fails with a
    clear error instead of hanging on input().
    """
    mode = os.getenv("MODE", "").strip().lower()
    if mode:
        return mode

    if not sys.stdin.isatty():
        logger.error(
            "MODE не задан и нет интерактивного терминала для выбора. "
            "Укажи MODE=%s в .env.", "|".join(_MODES),
        )
        return None

    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    console.print("[bold]Выберите режим:[/]")
    for key, (label, _) in _MODES.items():
        console.print(f"  [cyan]{key}[/] — {label}")
    return Prompt.ask("Режим", choices=list(_MODES.keys()))


async def main() -> None:
    debug = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
    bootstrap.configure_logging(debug, log_dir=os.getenv("LOG_DIR", ""))
    logger = logging.getLogger("main")
    bootstrap.log_crypto_backend(logger)

    mode = choose_mode(logger)
    if mode is None:
        sys.exit(1)
    if mode not in _MODES:
        logger.error("Неизвестный MODE=%r. Доступные: %s", mode, ", ".join(_MODES))
        sys.exit(1)

    label, module_path = _MODES[mode]
    logger.info("Режим: %s (MODE=%s)", label, mode)

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    bootstrap.setup_signal_handlers(shutdown_event, loop)

    module = importlib.import_module(module_path)
    await module.run(shutdown_event, logger)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Fallback for environments where signal handler didn't fire in time
        pass
