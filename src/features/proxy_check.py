"""
src/features/proxy_check.py — Standalone proxy-list health/speed check (MODE=check_proxies).

Reads a JSON proxy list (PROXY_LIST_JSON), checks every proxy concurrently
against a real Telegram DC (src.proxy.proxy_checker.check_all_proxies),
prints a results table, and optionally writes a JSON report
(PROXY_CHECK_REPORT_PATH).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from rich.console import Console
from rich.table import Table

import src.bootstrap as bootstrap
from src.proxy.proxy_checker import ProxyState, check_all_proxies
from src.proxy.proxy_list import load_proxies_from_json


def _render_results_table(proxies: List[Dict[str, Any]], results: List[ProxyState]) -> Table:
    table = Table(
        "Прокси",
        "Тип",
        "Активен",
        "Пинг (ms)",
        "Ошибка",
        title="[bold]Проверка прокси[/]",
        header_style="bold cyan",
        show_lines=True,
    )
    for proxy_config, state in zip(proxies, results):
        label = f"{proxy_config['host']}:{proxy_config['port']}"
        if state.is_active:
            table.add_row(
                label, state.proxy_type.value.upper(), "[green]Да[/]", f"{state.latency_ms:.0f}", "—",
            )
        else:
            table.add_row(
                label, state.proxy_type.value.upper(), "[red]Нет[/]", "—",
                (state.error_message or "")[:60],
            )
    return table


def _state_to_dict(proxy_config: Dict[str, Any], state: ProxyState) -> dict:
    return {
        "host": proxy_config.get("host"),
        "port": proxy_config.get("port"),
        "type": state.proxy_type.value,
        "is_active": state.is_active,
        "latency_ms": state.latency_ms,
        "error": state.error_message,
    }


async def run(shutdown_event, logger: logging.Logger) -> None:
    list_path = os.getenv("PROXY_LIST_JSON", "").strip()
    if not list_path:
        logger.error("PROXY_LIST_JSON не задан — укажи путь к JSON-списку прокси.")
        return

    try:
        proxies = load_proxies_from_json(list_path)
    except (OSError, ValueError) as exc:
        logger.error("Не удалось прочитать %s: %s", list_path, exc)
        return

    if not proxies:
        logger.warning("Список прокси пуст: %s", list_path)
        return

    concurrency = bootstrap.env_int("PROXY_CHECK_CONCURRENCY", "10")
    logger.info("Проверка %d прокси (concurrency=%d)…", len(proxies), concurrency)

    results = await check_all_proxies(proxies, concurrency=concurrency)

    Console().print(_render_results_table(proxies, results))

    alive = sum(1 for r in results if r.is_active)
    logger.info("Проверка завершена: %d/%d прокси активны.", alive, len(results))

    report_path = os.getenv("PROXY_CHECK_REPORT_PATH", "").strip()
    if report_path:
        payload = [_state_to_dict(p, s) for p, s in zip(proxies, results)]
        out = Path(report_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Отчёт сохранён: %s", out)
