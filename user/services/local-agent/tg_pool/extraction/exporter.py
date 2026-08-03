"""
tg_pool/exporter.py — Excel Export Module.

DataExporter накапливает ParsedUser и предоставляет три способа экспорта:

  export_summary(path)       — один Excel-файл со всеми пользователями
  export_by_source(dir)      — отдельный файл на каждый источник
  export_full(path)          — один файл с листом "Все" + по листу на источник

Дедупликация по user_id выполняется в add(): сводный список содержит
каждого пользователя один раз; источники хранятся отдельно и могут
пересекаться.

Требования: pandas>=2.0.0, openpyxl>=3.1.0
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Set

import pandas as pd

from tg_pool.extraction.data_extraction import ParsedUser
from tg_pool.extraction.user_filter import infer_gender, status_to_datetime

if TYPE_CHECKING:
    from tg_pool.scripting.lua_engine import LuaEngine

logger = logging.getLogger(__name__)

ColumnHook = Callable[[ParsedUser], Dict[str, Any]]

_COLUMNS = [
    "ID",
    "Имя",
    "Фамилия",
    "Юзернейм",
    "Телефон",
    "Пол",
    "Последний онлайн",
    "Аватар",
    "Premium",
    "Бот",
    "Источник",
]

_INVALID_SHEET_NAME_CHARS = frozenset(r"\/*?:[]")


def _unique_sheet_name(source: str, used_names: Set[str]) -> str:
    """Return an Excel-safe, case-insensitively unique worksheet name."""
    cleaned = "".join("_" if char in _INVALID_SHEET_NAME_CHARS else char for char in source)
    cleaned = cleaned.strip().strip("'") or "Source"
    base = cleaned[:31]
    candidate = base
    number = 2

    while candidate.casefold() in used_names:
        suffix = f"_{number}"
        candidate = f"{base[:31 - len(suffix)]}{suffix}"
        number += 1

    used_names.add(candidate.casefold())
    return candidate


def _user_to_row(user: ParsedUser, column_hook: Optional[ColumnHook] = None) -> dict:
    last_seen = status_to_datetime(user.status)
    row = {
        "ID":               user.user_id,
        "Имя":              user.first_name,
        "Фамилия":          user.last_name,
        "Юзернейм":         f"@{user.username}" if user.username else "",
        "Телефон":          user.phone,
        "Пол":              infer_gender(user.first_name, user.last_name),
        "Последний онлайн": last_seen.strftime("%Y-%m-%d %H:%M:%S UTC") if last_seen else "",
        "Аватар":           "Да" if user.has_photo else "Нет",
        "Premium":          "Да" if user.premium else "Нет",
        "Бот":              "Да" if user.bot else "Нет",
        "Источник":         user.source,
    }
    if column_hook is not None:
        try:
            row.update(column_hook(user))
        except Exception:
            logger.warning("column_hook failed for user_id=%s", user.user_id, exc_info=True)
    return row


class LuaColumnHook:
    """
    Adapter over LuaEngine.call() usable as DataExporter's column_hook --
    lets operators add custom Excel columns via a hot-reloadable script
    instead of Python code, same payload contract as LuaScriptFilter
    (tg_pool/extraction/user_filter.py).

    Script contract: `return function(user) return {column_name = value, ...} end`.
    """

    def __init__(self, engine: "LuaEngine", script_name: str) -> None:
        self._engine = engine
        self._script_name = script_name

    def __call__(self, user: ParsedUser) -> Dict[str, Any]:
        payload = {
            "user_id": user.user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "premium": user.premium,
            "has_photo": user.has_photo,
            "bot": user.bot,
            "source": user.source,
        }
        result = self._engine.call(self._script_name, payload)
        return dict(result.items()) if result is not None else {}


class DataExporter:
    """
    Накапливает ParsedUser и экспортирует их в Excel.

    add() принимает любой ParsedUser; пользователь добавляется в сводный
    список только один раз (по user_id), но в источниковые списки — каждый раз.
    """

    def __init__(self, column_hook: Optional[ColumnHook] = None) -> None:
        self._seen_ids: Set[int] = set()
        self._all: List[ParsedUser] = []
        self._by_source: Dict[str, List[ParsedUser]] = {}
        self._column_hook = column_hook

    def add(self, user: ParsedUser) -> None:
        self._by_source.setdefault(user.source, []).append(user)
        if user.user_id not in self._seen_ids:
            self._seen_ids.add(user.user_id)
            self._all.append(user)

    def add_many(self, users: Iterable[ParsedUser]) -> None:
        for u in users:
            self.add(u)

    def to_dataframe(self, users: Optional[List[ParsedUser]] = None) -> pd.DataFrame:
        """Строит DataFrame из переданного списка или из внутреннего сводного."""
        rows = [_user_to_row(u, self._column_hook) for u in (users if users is not None else self._all)]
        if self._column_hook is None:
            return pd.DataFrame(rows, columns=_COLUMNS)

        columns = list(_COLUMNS)
        seen = set(columns)
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    columns.append(key)
        return pd.DataFrame(rows, columns=columns)

    # ------------------------------------------------------------------
    # Export methods
    # ------------------------------------------------------------------

    def export_summary(self, path: Path) -> Path:
        """
        Один Excel-файл: все накопленные пользователи (без дублей по ID).

        Возвращает путь к созданному файлу.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df = self.to_dataframe()

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Все", index=False)

        logger.info("export_summary: %d rows → %s", len(df), path)
        return path

    def export_by_source(self, output_dir: Path) -> Dict[str, Path]:
        """
        По одному файлу на источник.

        Имя файла: <source>.xlsx с заменой спецсимволов на '_'.
        Возвращает словарь {source: path}.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result: Dict[str, Path] = {}

        for source, users in self._by_source.items():
            safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in source)
            file_path = output_dir / f"{safe_name}.xlsx"
            df = self.to_dataframe(users)

            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="Пользователи", index=False)

            logger.info("export_by_source: %s — %d rows → %s", source, len(df), file_path)
            result[source] = file_path

        return result

    def export_full(self, output_path: Path) -> Path:
        """
        Один файл с несколькими листами:
          "Все"          — дедуплицированный сводный список
          "<source>"     — пользователи конкретного источника

        Длинные имена листов обрезаются до 31 символа (ограничение Excel).
        Возвращает путь к созданному файлу.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            self.to_dataframe().to_excel(writer, sheet_name="Все", index=False)
            used_sheet_names = {name.casefold() for name in writer.book.sheetnames}

            for source, users in self._by_source.items():
                sheet_name = _unique_sheet_name(source, used_sheet_names)
                self.to_dataframe(users).to_excel(writer, sheet_name=sheet_name, index=False)

        logger.info(
            "export_full: %d users, %d sources → %s",
            len(self._all), len(self._by_source), output_path,
        )
        return output_path

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def total(self) -> int:
        return len(self._all)

    @property
    def sources(self) -> List[str]:
        return list(self._by_source.keys())

    def stats(self) -> Dict[str, int]:
        """Breakdown of the deduplicated summary list, for the end-of-run report
        (tg_pool.api.parsing.ParsingManager) -- how many collected users are
        actually reachable by username vs phone vs neither."""
        with_username = sum(1 for u in self._all if u.username)
        with_phone = sum(1 for u in self._all if u.phone)
        return {
            "total": len(self._all),
            "with_username": with_username,
            "without_username": len(self._all) - with_username,
            "with_phone": with_phone,
            "premium": sum(1 for u in self._all if u.premium),
            "bots": sum(1 for u in self._all if u.bot),
        }

    def export_sqlite(self, path: Path) -> Path:
        """
        Dumps the deduplicated summary list into a standalone SQLite file --
        one per parsing run (see ParsingManager), so a specific run's results
        stay queryable/reusable by other features without re-running the job
        or hunting through overwritten Excel exports.
        """
        import sqlite3

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT,
                    premium INTEGER NOT NULL,
                    has_photo INTEGER NOT NULL,
                    bot INTEGER NOT NULL,
                    source TEXT
                )
                """
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO users
                    (user_id, username, first_name, last_name, phone, premium, has_photo, bot, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        u.user_id, u.username, u.first_name, u.last_name, u.phone,
                        int(u.premium), int(u.has_photo), int(u.bot), u.source,
                    )
                    for u in self._all
                ],
            )
            conn.commit()

        logger.info("export_sqlite: %d users → %s", len(self._all), path)
        return path

    def export_txt(self, path: Path) -> Path:
        """
        Human-readable ("Notepad") list of the collected audience -- for a
        person to open and scan, not for another feature to parse (use the
        Excel or SQLite export for that; both are already picked up
        elsewhere as loadable audience databases). Users with a username
        sort first, alphabetically -- they're the ones you can act on
        directly -- everyone else follows sorted by ID. Missing fields show
        as "-" instead of blank/doubled-comma CSV noise, and the source
        column is dropped entirely when every user came from the same place,
        since repeating one link on thousands of lines is just noise.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        users = sorted(
            self._all,
            key=lambda u: (u.username == "", u.username.casefold(), u.user_id),
        )
        show_source = len({u.source for u in self._all}) > 1

        def cell(value: str) -> str:
            return value if value else "-"

        headers = ["ID", "Юзернейм", "Телефон"] + (["Источник"] if show_source else [])
        rows = [
            [
                str(u.user_id),
                cell(f"@{u.username}" if u.username else ""),
                cell(u.phone),
                *([cell(u.source)] if show_source else []),
            ]
            for u in users
        ]

        widths = [
            max(len(headers[i]), max((len(row[i]) for row in rows), default=0))
            for i in range(len(headers))
        ]

        def format_row(cells: List[str]) -> str:
            return "  ".join(value.ljust(width) for value, width in zip(cells, widths))

        lines = [format_row(headers), format_row(["-" * w for w in widths])]
        lines.extend(format_row(row) for row in rows)

        path.write_text("\n".join(lines), encoding="utf-8-sig")
        logger.info("export_txt: %d users → %s", len(self._all), path)
        return path
