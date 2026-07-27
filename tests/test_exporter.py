"""
tests/test_exporter.py — Unit tests for src/exporter.py.

Scenarios:
  DataFrame structure:
    1.  Empty exporter produces DataFrame with all required columns
    2.  Single user → correct column values in DataFrame
    3.  Юзернейм prefixed with @
    4.  Empty username → empty string (no @)
    5.  has_photo → "Да" / "Нет"
    6.  premium → "Да" / "Нет"
    7.  Gender inferred correctly for known names

  Deduplication:
    8.  Same user_id added twice → appears once in summary
    9.  Different user_ids → both appear
    10. Per-source lists not deduplicated (same user in two sources → appears in both)

  export_summary:
    11. Creates a file at the given path
    12. File contains one sheet named "Все"
    13. Sheet has correct number of rows
    14. Output directory is created if absent

  export_by_source:
    15. Creates one file per source
    16. Each file has sheet "Пользователи"
    17. Returns correct dict mapping source → path
    18. Special characters in source name are replaced with _

  export_full:
    19. Creates file with sheet "Все"
    20. Creates per-source sheets
    21. Sheet "Все" row count equals deduplicated total
    22. Per-source sheets may have more rows than "Все" (overlapping users)
    23. Long source names are truncated to 31 characters

  DataExporter.total / .sources:
    24. .total reflects deduplicated count
    25. .sources lists all added sources
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.extraction.data_extraction import ParsedUser
from src.extraction.exporter import DataExporter, LuaColumnHook, _COLUMNS
from src.scripting.lua_engine import LuaEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(
    user_id: int = 1,
    username: str = "alice",
    first_name: str = "Анна",
    last_name: str = "Иванова",
    phone: str = "+79001234567",
    premium: bool = False,
    has_photo: bool = True,
    status=None,
    source: str = "@group",
) -> ParsedUser:
    return ParsedUser(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        premium=premium,
        has_photo=has_photo,
        status=status,
        source=source,
    )


def read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet)


# ---------------------------------------------------------------------------
# DataFrame structure tests
# ---------------------------------------------------------------------------

class TestDataFrame:
    def test_empty_has_correct_columns(self):
        exp = DataExporter()
        df = exp.to_dataframe()
        assert list(df.columns) == _COLUMNS
        assert len(df) == 0

    def test_single_user_values(self):
        exp = DataExporter()
        user = make_user(user_id=42, username="alice", first_name="Анна", last_name="Иванова",
                         phone="+79001234567", premium=False, has_photo=True)
        exp.add(user)
        df = exp.to_dataframe()

        assert df.iloc[0]["ID"] == 42
        assert df.iloc[0]["Имя"] == "Анна"
        assert df.iloc[0]["Фамилия"] == "Иванова"
        assert df.iloc[0]["Юзернейм"] == "@alice"
        assert df.iloc[0]["Телефон"] == "+79001234567"

    def test_username_prefixed_with_at(self):
        exp = DataExporter()
        exp.add(make_user(username="bob"))
        df = exp.to_dataframe()
        assert df.iloc[0]["Юзернейм"] == "@bob"

    def test_empty_username_no_prefix(self):
        exp = DataExporter()
        exp.add(make_user(username=""))
        df = exp.to_dataframe()
        assert df.iloc[0]["Юзернейм"] == ""

    def test_has_photo_yes_no(self):
        exp = DataExporter()
        exp.add(make_user(user_id=1, has_photo=True))
        exp.add(make_user(user_id=2, has_photo=False))
        df = exp.to_dataframe()
        assert df[df["ID"] == 1].iloc[0]["Аватар"] == "Да"
        assert df[df["ID"] == 2].iloc[0]["Аватар"] == "Нет"

    def test_premium_yes_no(self):
        exp = DataExporter()
        exp.add(make_user(user_id=1, premium=True))
        exp.add(make_user(user_id=2, premium=False))
        df = exp.to_dataframe()
        assert df[df["ID"] == 1].iloc[0]["Premium"] == "Да"
        assert df[df["ID"] == 2].iloc[0]["Premium"] == "Нет"

    def test_gender_inferred_female(self):
        exp = DataExporter()
        exp.add(make_user(first_name="Анна", last_name="Иванова"))
        df = exp.to_dataframe()
        assert df.iloc[0]["Пол"] == "female"

    def test_gender_inferred_male(self):
        exp = DataExporter()
        exp.add(make_user(first_name="Иван", last_name="Иванов"))
        df = exp.to_dataframe()
        assert df.iloc[0]["Пол"] == "male"


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_same_user_id_added_once_to_summary(self):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@group1"))
        exp.add(make_user(user_id=1, source="@group2"))
        assert exp.total == 1
        df = exp.to_dataframe()
        assert len(df) == 1

    def test_different_ids_both_appear(self):
        exp = DataExporter()
        exp.add(make_user(user_id=1))
        exp.add(make_user(user_id=2))
        assert exp.total == 2

    def test_per_source_not_deduplicated(self):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@src1"))
        exp.add(make_user(user_id=1, source="@src2"))
        # Same user appears in both per-source lists
        assert len(exp._by_source["@src1"]) == 1
        assert len(exp._by_source["@src2"]) == 1

    def test_add_many(self):
        exp = DataExporter()
        users = [make_user(user_id=i) for i in range(5)]
        exp.add_many(users)
        assert exp.total == 5


# ---------------------------------------------------------------------------
# export_summary tests
# ---------------------------------------------------------------------------

class TestExportSummary:
    def test_creates_file(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user())
        out = tmp_path / "summary.xlsx"
        result = exp.export_summary(out)
        assert result.exists()

    def test_has_sheet_all(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user())
        out = tmp_path / "summary.xlsx"
        exp.export_summary(out)
        df = read_sheet(out, "Все")
        assert list(df.columns) == _COLUMNS

    def test_correct_row_count(self, tmp_path):
        exp = DataExporter()
        for i in range(5):
            exp.add(make_user(user_id=i))
        out = tmp_path / "summary.xlsx"
        exp.export_summary(out)
        df = read_sheet(out, "Все")
        assert len(df) == 5

    def test_creates_parent_dir(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user())
        out = tmp_path / "subdir" / "deep" / "summary.xlsx"
        exp.export_summary(out)
        assert out.exists()


# ---------------------------------------------------------------------------
# export_by_source tests
# ---------------------------------------------------------------------------

class TestExportBySource:
    def test_creates_one_file_per_source(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@src1"))
        exp.add(make_user(user_id=2, source="@src2"))
        result = exp.export_by_source(tmp_path)
        assert len(result) == 2

    def test_each_file_has_users_sheet(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@group"))
        result = exp.export_by_source(tmp_path)
        path = result["@group"]
        df = read_sheet(path, "Пользователи")
        assert list(df.columns) == _COLUMNS

    def test_returns_source_to_path_mapping(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@alpha"))
        result = exp.export_by_source(tmp_path)
        assert "@alpha" in result
        assert result["@alpha"].exists()

    def test_special_chars_in_source_replaced(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="https://t.me/testchat"))
        result = exp.export_by_source(tmp_path)
        path = list(result.values())[0]
        # Must not fail on special characters in filename
        assert path.exists()
        # No colon or slash in the filename
        assert ":" not in path.name
        assert "/" not in path.name


# ---------------------------------------------------------------------------
# export_full tests
# ---------------------------------------------------------------------------

class TestExportFull:
    def test_has_sheet_all(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@src"))
        out = tmp_path / "full.xlsx"
        exp.export_full(out)
        df = read_sheet(out, "Все")
        assert list(df.columns) == _COLUMNS

    def test_has_per_source_sheets(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@chat1"))
        exp.add(make_user(user_id=2, source="@chat2"))
        out = tmp_path / "full.xlsx"
        exp.export_full(out)
        with pd.ExcelFile(out) as xl:
            assert "Все" in xl.sheet_names
            assert "@chat1" in xl.sheet_names
            assert "@chat2" in xl.sheet_names

    def test_all_sheet_is_deduped(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@s1"))
        exp.add(make_user(user_id=1, source="@s2"))  # duplicate
        out = tmp_path / "full.xlsx"
        exp.export_full(out)
        df = read_sheet(out, "Все")
        assert len(df) == 1  # only 1 unique user

    def test_source_sheets_include_overlapping_users(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@s1"))
        exp.add(make_user(user_id=1, source="@s2"))
        out = tmp_path / "full.xlsx"
        exp.export_full(out)
        df_s1 = read_sheet(out, "@s1")
        df_s2 = read_sheet(out, "@s2")
        assert len(df_s1) == 1
        assert len(df_s2) == 1

    def test_long_source_name_truncated(self, tmp_path):
        long_source = "A" * 50  # Exceeds Excel 31-char limit
        exp = DataExporter()
        exp.add(make_user(user_id=1, source=long_source))
        out = tmp_path / "full.xlsx"
        exp.export_full(out)
        with pd.ExcelFile(out) as xl:
            for name in xl.sheet_names:
                assert len(name) <= 31

    def test_invalid_excel_characters_in_source_are_replaced(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="https://t.me/Unity3dDevs"))
        out = tmp_path / "full.xlsx"

        exp.export_full(out)

        with pd.ExcelFile(out) as xl:
            assert "https___t.me_Unity3dDevs" in xl.sheet_names

    def test_truncated_source_sheet_names_remain_unique(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="A" * 31 + "one"))
        exp.add(make_user(user_id=2, source="A" * 31 + "two"))
        out = tmp_path / "full.xlsx"

        exp.export_full(out)

        with pd.ExcelFile(out) as xl:
            source_sheets = xl.sheet_names[1:]
            assert len(source_sheets) == 2
            assert len({name.casefold() for name in source_sheets}) == 2
            assert all(len(name) <= 31 for name in source_sheets)


# ---------------------------------------------------------------------------
# DataExporter properties
# ---------------------------------------------------------------------------

class TestDataExporterProperties:
    def test_total_reflects_deduped_count(self):
        exp = DataExporter()
        exp.add(make_user(user_id=1))
        exp.add(make_user(user_id=1))  # duplicate
        exp.add(make_user(user_id=2))
        assert exp.total == 2

    def test_sources_lists_all_added(self):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@a"))
        exp.add(make_user(user_id=2, source="@b"))
        assert set(exp.sources) == {"@a", "@b"}

    def test_empty_exporter_total_zero(self):
        exp = DataExporter()
        assert exp.total == 0
        assert exp.sources == []


# ---------------------------------------------------------------------------
# stats() — end-of-run report breakdown (src.api.parsing._write_report)
# ---------------------------------------------------------------------------

class TestStats:
    def test_empty_exporter(self):
        assert DataExporter().stats() == {
            "total": 0, "with_username": 0, "without_username": 0,
            "with_phone": 0, "premium": 0, "bots": 0,
        }

    def test_counts_username_and_phone_independently(self):
        exp = DataExporter()
        exp.add(make_user(user_id=1, username="alice", phone="+7001"))
        exp.add(make_user(user_id=2, username="", phone="+7002"))
        exp.add(make_user(user_id=3, username="bob", phone=""))

        stats = exp.stats()
        assert stats["total"] == 3
        assert stats["with_username"] == 2
        assert stats["without_username"] == 1
        assert stats["with_phone"] == 2

    def test_counts_premium_and_bots(self):
        exp = DataExporter()
        exp.add(make_user(user_id=1, premium=True))
        exp.add(ParsedUser(user_id=2, bot=True, source="@group"))
        exp.add(make_user(user_id=3))

        stats = exp.stats()
        assert stats["premium"] == 1
        assert stats["bots"] == 1

    def test_deduplicated_users_counted_once(self):
        exp = DataExporter()
        exp.add(make_user(user_id=1, username="alice"))
        exp.add(make_user(user_id=1, username="alice"))
        assert exp.stats()["total"] == 1


# ---------------------------------------------------------------------------
# export_sqlite() — one queryable, never-overwritten DB file per run
# ---------------------------------------------------------------------------

class TestExportSqlite:
    def test_creates_file_with_correct_row_count(self, tmp_path):
        import sqlite3

        exp = DataExporter()
        exp.add(make_user(user_id=1, username="alice"))
        exp.add(make_user(user_id=2, username="bob"))
        path = tmp_path / "run.db"

        result = exp.export_sqlite(path)

        assert result == path
        assert path.exists()
        with sqlite3.connect(path) as conn:
            rows = conn.execute("SELECT user_id, username FROM users ORDER BY user_id").fetchall()
        assert rows == [(1, "alice"), (2, "bob")]

    def test_creates_parent_directory(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1))
        path = tmp_path / "nested" / "run.db"

        exp.export_sqlite(path)

        assert path.exists()

    def test_deduplicated_users_only(self, tmp_path):
        import sqlite3

        exp = DataExporter()
        exp.add(make_user(user_id=1, username="alice"))
        exp.add(make_user(user_id=1, username="alice"))  # duplicate
        path = tmp_path / "run.db"

        exp.export_sqlite(path)

        with sqlite3.connect(path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert count == 1

    def test_empty_exporter_creates_empty_table(self, tmp_path):
        import sqlite3

        path = tmp_path / "empty.db"
        DataExporter().export_sqlite(path)

        with sqlite3.connect(path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert count == 0


class TestExportTxt:
    def test_formats_as_aligned_human_readable_columns(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, username="alice", phone="+79001234567", source="@group"))
        exp.add(make_user(user_id=2, username="", phone="", source="@group"))
        path = tmp_path / "run.txt"

        result = exp.export_txt(path)

        assert result == path
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        # single shared source across every user -> no "Источник" column
        assert lines[0].split() == ["ID", "Юзернейм", "Телефон"]
        assert "@alice" in lines[2]
        assert lines[3].split() == ["2", "-", "-"]

    def test_users_with_username_sort_first_alphabetically(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, username="zoe"))
        exp.add(make_user(user_id=2, username=""))
        exp.add(make_user(user_id=3, username="alice"))
        path = tmp_path / "run.txt"

        exp.export_txt(path)
        rows = path.read_text(encoding="utf-8-sig").splitlines()[2:]

        assert [row.split()[0] for row in rows] == ["3", "1", "2"]

    def test_missing_username_and_phone_render_as_dash(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, username="", phone=""))
        path = tmp_path / "run.txt"

        exp.export_txt(path)
        row = path.read_text(encoding="utf-8-sig").splitlines()[2]

        assert row.split() == ["1", "-", "-"]

    def test_source_column_dropped_when_every_user_shares_one_source(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@group"))
        exp.add(make_user(user_id=2, username="bob", source="@group"))
        path = tmp_path / "run.txt"

        exp.export_txt(path)
        header = path.read_text(encoding="utf-8-sig").splitlines()[0]

        assert "Источник" not in header

    def test_source_column_kept_when_users_came_from_different_sources(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, source="@group_a"))
        exp.add(make_user(user_id=2, username="bob", source="@group_b"))
        path = tmp_path / "run.txt"

        exp.export_txt(path)
        lines = path.read_text(encoding="utf-8-sig").splitlines()

        assert "Источник" in lines[0]
        assert any("@group_a" in row for row in lines[2:])
        assert any("@group_b" in row for row in lines[2:])

    def test_creates_parent_directory(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1))
        path = tmp_path / "nested" / "run.txt"

        exp.export_txt(path)

        assert path.exists()

    def test_deduplicated_users_only(self, tmp_path):
        exp = DataExporter()
        exp.add(make_user(user_id=1, username="alice"))
        exp.add(make_user(user_id=1, username="alice"))  # duplicate
        path = tmp_path / "run.txt"

        exp.export_txt(path)

        # header + separator + exactly one data row
        assert len(path.read_text(encoding="utf-8-sig").splitlines()) == 3


# ---------------------------------------------------------------------------
# column_hook / LuaColumnHook — custom export columns
# ---------------------------------------------------------------------------

class TestColumnHook:
    def test_hook_adds_extra_columns(self):
        exp = DataExporter(column_hook=lambda u: {"VIP": u.user_id > 100})
        exp.add(make_user(user_id=150))

        df = exp.to_dataframe()

        assert "VIP" in df.columns
        assert df.iloc[0]["VIP"] == True  # noqa: E712 -- pandas stores bool as numpy.bool_

    def test_no_hook_keeps_original_columns_exactly(self):
        exp = DataExporter()
        exp.add(make_user())

        df = exp.to_dataframe()

        assert list(df.columns) == _COLUMNS

    def test_hook_can_override_standard_column(self):
        exp = DataExporter(column_hook=lambda u: {"Пол": "не определён"})
        exp.add(make_user())

        df = exp.to_dataframe()

        assert df.iloc[0]["Пол"] == "не определён"
        assert list(df.columns) == _COLUMNS

    def test_failing_hook_does_not_crash_export(self):
        def bad_hook(user):
            raise RuntimeError("boom")

        exp = DataExporter(column_hook=bad_hook)
        exp.add(make_user())

        df = exp.to_dataframe()

        assert len(df) == 1

    def test_hook_receiving_no_new_columns_is_a_noop(self):
        exp = DataExporter(column_hook=lambda u: {})
        exp.add(make_user())

        df = exp.to_dataframe()

        assert list(df.columns) == _COLUMNS


class TestLuaColumnHook:
    def test_adds_column_from_script(self, tmp_path):
        (tmp_path / "vip_tag.lua").write_text(
            "return function(user) return {VIP = user.user_id > 100} end",
            encoding="utf-8",
        )
        engine = LuaEngine(str(tmp_path))
        exp = DataExporter(column_hook=LuaColumnHook(engine, "vip_tag"))
        exp.add(make_user(user_id=150))
        exp.add(make_user(user_id=50, source="@other"))

        df = exp.to_dataframe()

        by_id = df.set_index("ID")["VIP"]
        assert bool(by_id[150]) is True
        assert bool(by_id[50]) is False

    def test_script_can_add_multiple_columns(self, tmp_path):
        (tmp_path / "multi.lua").write_text(
            "return function(user) return {ColA = 'x', ColB = 42} end",
            encoding="utf-8",
        )
        engine = LuaEngine(str(tmp_path))
        exp = DataExporter(column_hook=LuaColumnHook(engine, "multi"))
        exp.add(make_user())

        df = exp.to_dataframe()

        assert df.iloc[0]["ColA"] == "x"
        assert df.iloc[0]["ColB"] == 42
