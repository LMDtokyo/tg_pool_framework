"""
tg_pool/user_filter.py — User Filter Pipeline.

Конвейер фильтрации ParsedUser.

Фильтры:
  LastSeenFilter(days, hours)  — активность не раньше N дней/часов назад
  HasAvatarFilter              — только пользователи с аватаром
  IsPremiumFilter              — только Telegram Premium
  GenderFilter(target)         — "male", "female" или "unknown"

Вспомогательные функции:
  infer_gender(first_name, last_name) → "male" | "female" | "unknown"
  status_to_datetime(status)          → datetime | None   (для экспорта)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Iterable, List, Optional

from telethon.tl.types import (
    UserStatusLastMonth,
    UserStatusLastWeek,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)

from tg_pool.extraction.data_extraction import ParsedUser

if TYPE_CHECKING:
    from tg_pool.scripting.lua_engine import LuaEngine


# ---------------------------------------------------------------------------
# Gender heuristic
# ---------------------------------------------------------------------------

# Мужские имена-исключения, оканчивающиеся на -а/-я
_MALE_NAME_EXCEPTIONS = frozenset({
    "никита", "илья", "кузьма", "лука", "фома", "миша",
    "саша", "женя", "валя", "коля", "серёжа", "дима",
})

_FEMALE_LAST_SUFFIXES = ("ова", "ева", "ина", "яя", "цкая", "ская", "жская", "дская", "ная")
_MALE_LAST_SUFFIXES   = ("ов", "ев", "ин", "цкий", "ский", "жский", "дский", "ный", "ой", "ый", "ий")

_FEMALE_FIRST_SUFFIXES = ("ья", "ия", "ея", "ая", "яя")  # check before generic -а/-я
_VOWELS = frozenset("аеёиоуыэюя")
_MALE_CONS_FINAL = frozenset("бвгджзйклмнпрстфхцчшщ")


def infer_gender(first_name: Optional[str], last_name: Optional[str]) -> str:
    """
    Возвращает "male", "female" или "unknown".

    Алгоритм: взвешенное суммирование по окончаниям имени (вес 1) и
    фамилии (вес 2). Положительный счёт → female, отрицательный → male.
    """
    score = 0
    fn = (first_name or "").strip().lower()
    ln = (last_name or "").strip().lower()

    # --- Фамилия (вес 2) ---
    if ln:
        for suffix in _FEMALE_LAST_SUFFIXES:
            if ln.endswith(suffix):
                score += 2
                break
        else:
            for suffix in _MALE_LAST_SUFFIXES:
                if ln.endswith(suffix):
                    score -= 2
                    break

    # --- Имя (вес 1) ---
    if fn:
        if fn in _MALE_NAME_EXCEPTIONS:
            score -= 1
        else:
            # Check compound female endings first
            female_end = any(fn.endswith(s) for s in _FEMALE_FIRST_SUFFIXES)
            if female_end or (fn[-1] in _VOWELS and fn[-1] in "ая"):
                score += 1
            elif fn[-1] in _MALE_CONS_FINAL or fn[-1] == "й":
                score -= 1
            elif fn[-1] in _VOWELS and fn[-1] not in "ая":
                # Ends in е/и/о/у/ю/ё — neutral, skip
                pass

    if score > 0:
        return "female"
    if score < 0:
        return "male"
    return "unknown"


def status_to_datetime(status: Any) -> Optional[datetime]:
    """Конвертирует Telethon UserStatus в datetime (UTC) или None."""
    if isinstance(status, UserStatusOnline):
        return datetime.now(timezone.utc)
    if isinstance(status, UserStatusOffline) and status.was_online is not None:
        was = status.was_online
        if was.tzinfo is None:
            was = was.replace(tzinfo=timezone.utc)
        return was
    return None


# ---------------------------------------------------------------------------
# Абстрактный фильтр
# ---------------------------------------------------------------------------

class BaseFilter(ABC):
    @abstractmethod
    def matches(self, user: ParsedUser) -> bool:
        """True — пользователь проходит фильтр."""


# ---------------------------------------------------------------------------
# LastSeenFilter
# ---------------------------------------------------------------------------

class LastSeenFilter(BaseFilter):
    """
    Пропускает пользователей, которые были онлайн не ранее указанного
    временного окна.

    Порядок классификации Telethon UserStatus:
      UserStatusOnline    → онлайн прямо сейчас → всегда проходит
      UserStatusOffline   → есть точный was_online → сравниваем с окном
      UserStatusRecently  → "недавно" ≈ до 3 дней → проходит при hours >= 72
      UserStatusLastWeek  → последний раз в пределах недели → hours >= 168
      UserStatusLastMonth → в пределах месяца → hours >= 720
      UserStatusEmpty     → время скрыто → не проходит
    """

    def __init__(self, days: int = 0, hours: int = 0) -> None:
        total = days * 24 + hours
        if total <= 0:
            raise ValueError("LastSeenFilter requires days > 0 or hours > 0")
        self._hours = total

    def matches(self, user: ParsedUser) -> bool:
        status = user.status

        if isinstance(status, UserStatusOnline):
            return True

        if isinstance(status, UserStatusOffline):
            was = status.was_online
            if was is None:
                return False
            if was.tzinfo is None:
                was = was.replace(tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self._hours)
            return was >= cutoff

        if isinstance(status, UserStatusRecently):
            return self._hours >= 72

        if isinstance(status, UserStatusLastWeek):
            return self._hours >= 168

        if isinstance(status, UserStatusLastMonth):
            return self._hours >= 720

        # UserStatusEmpty или None — время скрыто
        return False


# ---------------------------------------------------------------------------
# HasAvatarFilter
# ---------------------------------------------------------------------------

class HasAvatarFilter(BaseFilter):
    def matches(self, user: ParsedUser) -> bool:
        return user.has_photo


# ---------------------------------------------------------------------------
# IsPremiumFilter
# ---------------------------------------------------------------------------

class IsPremiumFilter(BaseFilter):
    def matches(self, user: ParsedUser) -> bool:
        return user.premium


# ---------------------------------------------------------------------------
# IsBotFilter
# ---------------------------------------------------------------------------

class IsBotFilter(BaseFilter):
    """
    Фильтрует по признаку бота.

    is_bot=False (по умолчанию) — пропускает только реальных пользователей,
    исключая ботов. Это то, что нужно в подавляющем большинстве случаев
    парсинга под рассылку/аутрич.
    """

    def __init__(self, is_bot: bool = False) -> None:
        self.is_bot = is_bot

    def matches(self, user: ParsedUser) -> bool:
        return user.bot == self.is_bot


# ---------------------------------------------------------------------------
# GenderFilter
# ---------------------------------------------------------------------------

class GenderFilter(BaseFilter):
    """
    Фильтрует по полу.

    target: "male", "female" или "unknown"
    Гендер инферируется из first_name + last_name при каждой проверке.
    """

    def __init__(self, target: str) -> None:
        if target not in ("male", "female", "unknown"):
            raise ValueError(f"GenderFilter: invalid target={target!r}")
        self.target = target

    def matches(self, user: ParsedUser) -> bool:
        return infer_gender(user.first_name, user.last_name) == self.target


# ---------------------------------------------------------------------------
# LuaScriptFilter — predicate logic lives in an external, hot-reloadable script
# ---------------------------------------------------------------------------

class LuaScriptFilter(BaseFilter):
    """
    Filter whose predicate is a .lua script loaded by a LuaEngine, instead of
    Python code — lets operators tune filter logic without redeploying.

    Script contract: `return function(user) return <boolean> end`, where
    `user` is a plain table with fields: user_id, username, first_name,
    last_name, phone, premium, has_photo, bot, source, gender.
    """

    def __init__(self, engine: "LuaEngine", script_name: str) -> None:
        self._engine = engine
        self._script_name = script_name

    def matches(self, user: ParsedUser) -> bool:
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
            "gender": infer_gender(user.first_name, user.last_name),
        }
        return bool(self._engine.call(self._script_name, payload))


# ---------------------------------------------------------------------------
# UserFilterPipeline
# ---------------------------------------------------------------------------

class UserFilterPipeline:
    """
    Цепочка фильтров: пользователь проходит конвейер, только если
    все фильтры возвращают True (логическое И).

    Использование:
      pipeline = UserFilterPipeline([LastSeenFilter(days=7), HasAvatarFilter()])
      filtered = pipeline.apply(users)
    """

    def __init__(self, filters: Optional[List[BaseFilter]] = None) -> None:
        self._filters: List[BaseFilter] = list(filters or [])

    def add(self, f: BaseFilter) -> "UserFilterPipeline":
        self._filters.append(f)
        return self

    def passes(self, user: ParsedUser) -> bool:
        return all(f.matches(user) for f in self._filters)

    def apply(self, users: Iterable[ParsedUser]) -> List[ParsedUser]:
        return [u for u in users if self.passes(u)]
