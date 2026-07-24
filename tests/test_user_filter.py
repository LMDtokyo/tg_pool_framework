"""
tests/test_user_filter.py — Unit tests for src/user_filter.py.

Scenarios:
  infer_gender:
    1.  Female last name (-ова) inferred as female
    2.  Male last name (-ов) inferred as male
    3.  Female first name (Анна) inferred as female
    4.  Male first name (Александр) inferred as male
    5.  Female compound signal (Мария Петрова) → female
    6.  Male compound signal (Иван Петров) → male
    7.  Male name exception "Никита" → male
    8.  Empty names → unknown
    9.  Only last name, female → female
    10. Only last name, male → male

  LastSeenFilter:
    11. UserStatusOnline always passes
    12. UserStatusOffline within window passes
    13. UserStatusOffline beyond window fails
    14. UserStatusRecently with hours >= 72 passes
    15. UserStatusRecently with hours < 72 fails
    16. UserStatusLastWeek with hours >= 168 passes
    17. UserStatusLastWeek with hours < 168 fails
    18. UserStatusLastMonth with hours >= 720 passes
    19. UserStatusLastMonth with hours < 720 fails
    20. UserStatusEmpty fails
    21. status=None fails
    22. Invalid (days=0, hours=0) raises ValueError

  HasAvatarFilter:
    23. has_photo=True passes
    24. has_photo=False fails

  IsPremiumFilter:
    25. premium=True passes
    26. premium=False fails

  GenderFilter:
    27. Correct gender passes
    28. Wrong gender fails
    29. Unknown target="unknown" works

  UserFilterPipeline:
    30. Empty pipeline — all pass
    31. Single filter restricts correctly
    32. Two filters: AND logic
    33. apply() returns correct list
    34. Chaining add() returns self
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.extraction.data_extraction import ParsedUser
from src.extraction.user_filter import (
    BaseFilter,
    GenderFilter,
    HasAvatarFilter,
    IsBotFilter,
    IsPremiumFilter,
    LastSeenFilter,
    LuaScriptFilter,
    UserFilterPipeline,
    infer_gender,
    status_to_datetime,
)
from src.scripting.lua_engine import LuaEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(**kwargs) -> ParsedUser:
    defaults = dict(
        user_id=1,
        username="test",
        first_name="",
        last_name="",
        phone="",
        premium=False,
        has_photo=False,
        status=None,
        source="test",
    )
    defaults.update(kwargs)
    return ParsedUser(**defaults)


def _online_status():
    from telethon.tl.types import UserStatusOnline
    return UserStatusOnline(expires=0)


def _offline_status(delta_hours: float):
    from telethon.tl.types import UserStatusOffline
    was = datetime.now(timezone.utc) - timedelta(hours=delta_hours)
    return UserStatusOffline(was_online=was)


def _recently_status():
    from telethon.tl.types import UserStatusRecently
    return UserStatusRecently()


def _last_week_status():
    from telethon.tl.types import UserStatusLastWeek
    return UserStatusLastWeek()


def _last_month_status():
    from telethon.tl.types import UserStatusLastMonth
    return UserStatusLastMonth()


def _empty_status():
    from telethon.tl.types import UserStatusEmpty
    return UserStatusEmpty()


# ---------------------------------------------------------------------------
# infer_gender tests
# ---------------------------------------------------------------------------

class TestInferGender:
    def test_female_last_name_suffix_ova(self):
        assert infer_gender("", "Иванова") == "female"

    def test_male_last_name_suffix_ov(self):
        assert infer_gender("", "Иванов") == "male"

    def test_female_first_name_anna(self):
        # No last name signal; first name "Анна" ends in -а → female
        assert infer_gender("Анна", "") == "female"

    def test_male_first_name_aleksandr(self):
        # Ends in consonant 'р' → male
        assert infer_gender("Александр", "") == "male"

    def test_female_compound_signal(self):
        assert infer_gender("Мария", "Петрова") == "female"

    def test_male_compound_signal(self):
        assert infer_gender("Иван", "Петров") == "male"

    def test_male_exception_nikita(self):
        # "Никита" ends in -а but is in the exception list
        assert infer_gender("Никита", "") == "male"

    def test_empty_names_unknown(self):
        assert infer_gender("", "") == "unknown"

    def test_none_names_unknown(self):
        assert infer_gender(None, None) == "unknown"

    def test_only_female_last_name(self):
        assert infer_gender(None, "Смирнова") == "female"

    def test_only_male_last_name(self):
        assert infer_gender(None, "Смирнов") == "male"

    def test_female_patronymic_style_last_name(self):
        # -ская suffix
        assert infer_gender("", "Чайковская") == "female"

    def test_male_patronymic_style_last_name(self):
        # -ский suffix
        assert infer_gender("", "Чайковский") == "male"


# ---------------------------------------------------------------------------
# LastSeenFilter tests
# ---------------------------------------------------------------------------

class TestLastSeenFilter:
    def test_online_always_passes(self):
        f = LastSeenFilter(hours=1)
        user = make_user(status=_online_status())
        assert f.matches(user) is True

    def test_offline_within_window_passes(self):
        f = LastSeenFilter(hours=24)
        user = make_user(status=_offline_status(delta_hours=12))
        assert f.matches(user) is True

    def test_offline_beyond_window_fails(self):
        f = LastSeenFilter(hours=24)
        user = make_user(status=_offline_status(delta_hours=36))
        assert f.matches(user) is False

    def test_recently_passes_when_hours_ge_72(self):
        f = LastSeenFilter(hours=72)
        user = make_user(status=_recently_status())
        assert f.matches(user) is True

    def test_recently_fails_when_hours_lt_72(self):
        f = LastSeenFilter(hours=48)
        user = make_user(status=_recently_status())
        assert f.matches(user) is False

    def test_last_week_passes_when_hours_ge_168(self):
        f = LastSeenFilter(hours=168)
        user = make_user(status=_last_week_status())
        assert f.matches(user) is True

    def test_last_week_fails_when_hours_lt_168(self):
        f = LastSeenFilter(hours=100)
        user = make_user(status=_last_week_status())
        assert f.matches(user) is False

    def test_last_month_passes_when_hours_ge_720(self):
        f = LastSeenFilter(hours=720)
        user = make_user(status=_last_month_status())
        assert f.matches(user) is True

    def test_last_month_fails_when_hours_lt_720(self):
        f = LastSeenFilter(days=7)
        user = make_user(status=_last_month_status())
        assert f.matches(user) is False

    def test_empty_status_fails(self):
        f = LastSeenFilter(days=30)
        user = make_user(status=_empty_status())
        assert f.matches(user) is False

    def test_none_status_fails(self):
        f = LastSeenFilter(days=30)
        user = make_user(status=None)
        assert f.matches(user) is False

    def test_zero_hours_raises(self):
        with pytest.raises(ValueError):
            LastSeenFilter(days=0, hours=0)

    def test_days_and_hours_combined(self):
        # 1 day + 1 hour = 25 hours window
        f = LastSeenFilter(days=1, hours=1)
        user = make_user(status=_offline_status(delta_hours=24))
        assert f.matches(user) is True


# ---------------------------------------------------------------------------
# HasAvatarFilter tests
# ---------------------------------------------------------------------------

class TestHasAvatarFilter:
    def test_has_photo_passes(self):
        f = HasAvatarFilter()
        user = make_user(has_photo=True)
        assert f.matches(user) is True

    def test_no_photo_fails(self):
        f = HasAvatarFilter()
        user = make_user(has_photo=False)
        assert f.matches(user) is False


# ---------------------------------------------------------------------------
# IsPremiumFilter tests
# ---------------------------------------------------------------------------

class TestIsPremiumFilter:
    def test_premium_passes(self):
        f = IsPremiumFilter()
        user = make_user(premium=True)
        assert f.matches(user) is True

    def test_not_premium_fails(self):
        f = IsPremiumFilter()
        user = make_user(premium=False)
        assert f.matches(user) is False


# ---------------------------------------------------------------------------
# IsBotFilter tests
# ---------------------------------------------------------------------------

class TestIsBotFilter:
    def test_default_excludes_bots(self):
        f = IsBotFilter()
        assert f.matches(make_user(bot=False)) is True
        assert f.matches(make_user(bot=True)) is False

    def test_is_bot_true_keeps_only_bots(self):
        f = IsBotFilter(is_bot=True)
        assert f.matches(make_user(bot=True)) is True
        assert f.matches(make_user(bot=False)) is False


# ---------------------------------------------------------------------------
# GenderFilter tests
# ---------------------------------------------------------------------------

class TestGenderFilter:
    def test_correct_gender_passes(self):
        f = GenderFilter("female")
        user = make_user(first_name="Анна", last_name="Иванова")
        assert f.matches(user) is True

    def test_wrong_gender_fails(self):
        f = GenderFilter("male")
        user = make_user(first_name="Анна", last_name="Иванова")
        assert f.matches(user) is False

    def test_unknown_target_works(self):
        f = GenderFilter("unknown")
        user = make_user(first_name="", last_name="")
        assert f.matches(user) is True

    def test_invalid_target_raises(self):
        with pytest.raises(ValueError):
            GenderFilter("other")


# ---------------------------------------------------------------------------
# UserFilterPipeline tests
# ---------------------------------------------------------------------------

class TestUserFilterPipeline:
    def test_empty_pipeline_all_pass(self):
        pipeline = UserFilterPipeline()
        users = [make_user(user_id=i) for i in range(5)]
        result = pipeline.apply(users)
        assert len(result) == 5

    def test_single_filter_restricts(self):
        pipeline = UserFilterPipeline([HasAvatarFilter()])
        users = [
            make_user(user_id=1, has_photo=True),
            make_user(user_id=2, has_photo=False),
            make_user(user_id=3, has_photo=True),
        ]
        result = pipeline.apply(users)
        assert len(result) == 2
        assert all(u.has_photo for u in result)

    def test_two_filters_and_logic(self):
        pipeline = UserFilterPipeline([HasAvatarFilter(), IsPremiumFilter()])
        users = [
            make_user(user_id=1, has_photo=True, premium=True),   # passes
            make_user(user_id=2, has_photo=True, premium=False),  # fails premium
            make_user(user_id=3, has_photo=False, premium=True),  # fails avatar
            make_user(user_id=4, has_photo=False, premium=False), # fails both
        ]
        result = pipeline.apply(users)
        assert len(result) == 1
        assert result[0].user_id == 1

    def test_apply_returns_correct_list(self):
        pipeline = UserFilterPipeline([IsPremiumFilter()])
        users = [make_user(user_id=i, premium=(i % 2 == 0)) for i in range(6)]
        result = pipeline.apply(users)
        assert all(u.premium for u in result)
        assert len(result) == 3  # IDs 0, 2, 4

    def test_passes_method(self):
        pipeline = UserFilterPipeline([HasAvatarFilter()])
        assert pipeline.passes(make_user(has_photo=True)) is True
        assert pipeline.passes(make_user(has_photo=False)) is False

    def test_add_returns_self_for_chaining(self):
        pipeline = UserFilterPipeline()
        result = pipeline.add(HasAvatarFilter())
        assert result is pipeline

    def test_chained_add(self):
        pipeline = (
            UserFilterPipeline()
            .add(HasAvatarFilter())
            .add(IsPremiumFilter())
        )
        user = make_user(has_photo=True, premium=True)
        assert pipeline.passes(user) is True


# ---------------------------------------------------------------------------
# status_to_datetime tests
# ---------------------------------------------------------------------------

class TestStatusToDatetime:
    def test_online_returns_now(self):
        dt = status_to_datetime(_online_status())
        assert dt is not None
        assert abs((dt - datetime.now(timezone.utc)).total_seconds()) < 2

    def test_offline_returns_was_online(self):
        was = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        from telethon.tl.types import UserStatusOffline
        status = UserStatusOffline(was_online=was)
        dt = status_to_datetime(status)
        assert dt == was

    def test_recently_returns_none(self):
        assert status_to_datetime(_recently_status()) is None

    def test_empty_returns_none(self):
        assert status_to_datetime(_empty_status()) is None

    def test_none_returns_none(self):
        assert status_to_datetime(None) is None


# ---------------------------------------------------------------------------
# LuaScriptFilter
# ---------------------------------------------------------------------------

class TestLuaScriptFilter:
    def test_matches_delegates_to_lua_script(self, tmp_path):
        (tmp_path / "premium_only.lua").write_text(
            "return function(user) return user.premium == true end",
            encoding="utf-8",
        )
        engine = LuaEngine(str(tmp_path))
        filt = LuaScriptFilter(engine, "premium_only")

        assert filt.matches(make_user(premium=True)) is True
        assert filt.matches(make_user(premium=False)) is False

    def test_exposes_gender_field_to_script(self, tmp_path):
        (tmp_path / "female_only.lua").write_text(
            "return function(user) return user.gender == 'female' end",
            encoding="utf-8",
        )
        engine = LuaEngine(str(tmp_path))
        filt = LuaScriptFilter(engine, "female_only")

        assert filt.matches(make_user(first_name="Мария", last_name="Петрова")) is True
        assert filt.matches(make_user(first_name="Иван", last_name="Петров")) is False

    def test_composes_with_pipeline(self, tmp_path):
        (tmp_path / "has_username.lua").write_text(
            "return function(user) return user.username ~= '' end",
            encoding="utf-8",
        )
        engine = LuaEngine(str(tmp_path))
        pipeline = UserFilterPipeline([
            LuaScriptFilter(engine, "has_username"),
            IsPremiumFilter(),
        ])

        assert pipeline.passes(make_user(username="ivan", premium=True)) is True
        assert pipeline.passes(make_user(username="", premium=True)) is False
