"""
src/data_extraction.py — Data Extraction Module.

Паттерн Strategy для сбора пользователей из различных источников Telegram.

Стратегии:
  GroupMembersStrategy    — iter_participants (полный список участников)
  ChannelCommentsStrategy — комментарии к постам через reply_to
  GroupMessagesStrategy   — авторы сообщений из истории чата
  ReactionsStrategy       — пользователи, оставившие реакции
  PollsStrategy           — проголосовавшие в опросах
  SystemMessagesStrategy  — служебные события (вход/добавление в чат)
  TopicMessagesStrategy   — авторы сообщений в конкретном топике форума

list_forum_topics() возвращает список топиков форума (для выбора topic_id).

Все стратегии возвращают Set[ParsedUser], дедуплицируя по user_id.

Обратная совместимость:
  extract_members() сохраняет прежнюю сигнатуру → Set[str] (юзернеймы).
  Новый API extract_users() возвращает Set[ParsedUser] с полными метаданными.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine, List, Optional, Set

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    FloodWaitError,
)
from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
    GetMessageReactionsListRequest,
    GetPollVotesRequest,
)
from telethon.tl.types import (
    ForumTopic,
    MessageActionChatAddUser,
    MessageActionChatJoinedByLink,
    MessageService,
    ReactionEmoji,
    User,
)

from src.config import TimingPolicy
from src.extraction.entity_resolver import EntityKind, UniversalEntityResolver

if TYPE_CHECKING:
    from src.scripting.lua_engine import LuaEngine

logger = logging.getLogger(__name__)

_PAGE = 200


# ---------------------------------------------------------------------------
# ParsedUser — богатая модель участника
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class ParsedUser:
    """
    Участник Telegram с полными метаданными.

    Дедупликация в set выполняется по user_id (хэш и равенство определены явно).
    status — нативный объект Telethon UserStatus; используется фильтрами.
    """
    user_id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    premium: bool = False
    has_photo: bool = False
    bot: bool = False
    status: Any = field(default=None, repr=False)
    source: str = ""

    def __hash__(self) -> int:
        return hash(self.user_id)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ParsedUser):
            return self.user_id == other.user_id
        return NotImplemented


# ---------------------------------------------------------------------------
# Абстрактная стратегия
# ---------------------------------------------------------------------------

class BaseParsingStrategy(ABC):
    """
    Базовый класс для всех стратегий сбора участников.

    Параметры:
      limit     — максимальное число уникальных пользователей.
      delay     — пауза между запросами к API (сек).
    """

    def __init__(self, limit: int = 5_000, delay: float = 0.5) -> None:
        self.limit = limit
        self.delay = delay

    @abstractmethod
    async def collect(
        self,
        client: TelegramClient,
        entity: Any,
        source_label: str,
    ) -> Set[ParsedUser]:
        """Собрать участников из entity и вернуть их как set (дедуп по ID)."""

    @staticmethod
    def _from_user(user: Any, source: str) -> Optional[ParsedUser]:
        """Конвертировать Telethon User → ParsedUser. None для не-пользователей."""
        if user is None or not isinstance(user, User):
            return None
        return ParsedUser(
            user_id=user.id,
            username=user.username or "",
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            phone=user.phone or "",
            premium=bool(getattr(user, "premium", False)),
            has_photo=user.photo is not None,
            bot=bool(getattr(user, "bot", False)),
            status=user.status,
            source=source,
        )


# ---------------------------------------------------------------------------
# Стратегия 1: GroupMembersStrategy
# ---------------------------------------------------------------------------

class GroupMembersStrategy(BaseParsingStrategy):
    """iter_participants — полный список участников группы/супергруппы."""

    async def collect(
        self, client: TelegramClient, entity: Any, source_label: str
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        async for raw in client.iter_participants(entity, aggressive=False):
            parsed = self._from_user(raw, source_label)
            if parsed:
                users.add(parsed)
            if len(users) >= self.limit:
                break
            if len(users) % _PAGE == 0 and len(users):
                await asyncio.sleep(self.delay)
        logger.info("[GroupMembers] %s → %d users", source_label, len(users))
        return users


# ---------------------------------------------------------------------------
# Стратегия 2: ChannelCommentsStrategy
# ---------------------------------------------------------------------------

class ChannelCommentsStrategy(BaseParsingStrategy):
    """Читает комментарии к постам канала (reply_to=post_id)."""

    def __init__(self, limit: int = 5_000, delay: float = 0.5, max_posts: int = 50) -> None:
        super().__init__(limit, delay)
        self.max_posts = max_posts

    async def collect(
        self, client: TelegramClient, entity: Any, source_label: str
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()

        async for post in client.iter_messages(entity, limit=self.max_posts):
            if len(users) >= self.limit:
                break
            if not post.replies:
                continue

            async for comment in client.iter_messages(entity, reply_to=post.id):
                if comment.sender and isinstance(comment.sender, User):
                    parsed = self._from_user(comment.sender, source_label)
                    if parsed:
                        users.add(parsed)
                if len(users) >= self.limit:
                    break

            await asyncio.sleep(self.delay)

        logger.info("[ChannelComments] %s → %d users", source_label, len(users))
        return users


# ---------------------------------------------------------------------------
# Стратегия 3: GroupMessagesStrategy
# ---------------------------------------------------------------------------

class GroupMessagesStrategy(BaseParsingStrategy):
    """Сканирует историю чата, собирая авторов сообщений."""

    def __init__(self, limit: int = 5_000, delay: float = 0.5, scan_limit: int = 50_000) -> None:
        super().__init__(limit, delay)
        self.scan_limit = scan_limit

    async def collect(
        self, client: TelegramClient, entity: Any, source_label: str
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        scanned = 0

        async for msg in client.iter_messages(entity, limit=self.scan_limit):
            if isinstance(msg, MessageService):
                scanned += 1
                continue

            sender = msg.sender
            if isinstance(sender, User):
                parsed = self._from_user(sender, source_label)
                if parsed:
                    users.add(parsed)

            scanned += 1
            if scanned % _PAGE == 0:
                await asyncio.sleep(self.delay)
            if len(users) >= self.limit:
                break

        logger.info("[GroupMessages] %s → %d users (%d scanned)", source_label, len(users), scanned)
        return users


# ---------------------------------------------------------------------------
# Стратегия 4: ReactionsStrategy
# ---------------------------------------------------------------------------

class ReactionsStrategy(BaseParsingStrategy):
    """Пользователи, поставившие реакции на посты."""

    def __init__(self, limit: int = 5_000, delay: float = 0.5, max_posts: int = 20) -> None:
        super().__init__(limit, delay)
        self.max_posts = max_posts

    async def collect(
        self, client: TelegramClient, entity: Any, source_label: str
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        posts_checked = 0

        async for post in client.iter_messages(entity, limit=self.max_posts):
            if posts_checked >= self.max_posts or len(users) >= self.limit:
                break
            posts_checked += 1

            if not post.reactions:
                continue

            for rc in post.reactions.results:
                if not isinstance(rc.reaction, ReactionEmoji):
                    continue

                offset = ""
                while True:
                    try:
                        result = await client(GetMessageReactionsListRequest(
                            peer=entity,
                            id=post.id,
                            reaction=rc.reaction,
                            offset=offset,
                            limit=100,
                        ))
                    except Exception as exc:
                        logger.debug("[Reactions] skip reaction: %s", exc)
                        break

                    for raw_user in result.users:
                        parsed = self._from_user(raw_user, source_label)
                        if parsed:
                            users.add(parsed)

                    if not getattr(result, "next_offset", None):
                        break
                    offset = result.next_offset
                    await asyncio.sleep(self.delay)

                    if len(users) >= self.limit:
                        break

            await asyncio.sleep(self.delay)

        logger.info("[Reactions] %s → %d users", source_label, len(users))
        return users


# ---------------------------------------------------------------------------
# Стратегия 5: PollsStrategy
# ---------------------------------------------------------------------------

class PollsStrategy(BaseParsingStrategy):
    """Пользователи, проголосовавшие в опросах."""

    def __init__(self, limit: int = 5_000, delay: float = 0.5, max_polls: int = 10) -> None:
        super().__init__(limit, delay)
        self.max_polls = max_polls

    async def collect(
        self, client: TelegramClient, entity: Any, source_label: str
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        polls_found = 0

        async for msg in client.iter_messages(entity, limit=200):
            if polls_found >= self.max_polls or len(users) >= self.limit:
                break

            media = getattr(msg, "media", None)
            if media is None or not hasattr(media, "poll"):
                continue

            polls_found += 1
            poll = media.poll

            for answer in poll.answers:
                offset = b""
                while True:
                    try:
                        result = await client(GetPollVotesRequest(
                            peer=entity,
                            id=msg.id,
                            option=answer.option,
                            offset=offset,
                            limit=50,
                        ))
                    except Exception as exc:
                        logger.debug("[Polls] skip option: %s", exc)
                        break

                    for raw_user in result.users:
                        parsed = self._from_user(raw_user, source_label)
                        if parsed:
                            users.add(parsed)

                    if not getattr(result, "next_offset", None):
                        break
                    offset = result.next_offset
                    await asyncio.sleep(self.delay)

                    if len(users) >= self.limit:
                        break

            await asyncio.sleep(self.delay)

        logger.info("[Polls] %s → %d users", source_label, len(users))
        return users


# ---------------------------------------------------------------------------
# Стратегия 6: SystemMessagesStrategy
# ---------------------------------------------------------------------------

class SystemMessagesStrategy(BaseParsingStrategy):
    """
    Служебные сообщения типа MessageActionChatAddUser и
    MessageActionChatJoinedByLink — пользователи, вошедшие в чат.
    """

    async def collect(
        self, client: TelegramClient, entity: Any, source_label: str
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        seen_ids: Set[int] = set()
        scanned = 0

        async for msg in client.iter_messages(entity, limit=self.limit * 5):
            if not isinstance(msg, MessageService):
                scanned += 1
                continue

            action = msg.action
            uid_list: List[int] = []

            if isinstance(action, MessageActionChatAddUser):
                uid_list = list(action.users)
            elif isinstance(action, MessageActionChatJoinedByLink):
                from_id = getattr(msg, "from_id", None)
                if from_id and hasattr(from_id, "user_id"):
                    uid_list = [from_id.user_id]

            for uid in uid_list:
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                try:
                    raw_user = await client.get_entity(uid)
                    parsed = self._from_user(raw_user, source_label)
                    if parsed:
                        users.add(parsed)
                except Exception:
                    pass

            scanned += 1
            if scanned % _PAGE == 0:
                await asyncio.sleep(self.delay)
            if len(users) >= self.limit:
                break

        logger.info("[SystemMessages] %s → %d users", source_label, len(users))
        return users


# ---------------------------------------------------------------------------
# Стратегия 7: TopicMessagesStrategy
# ---------------------------------------------------------------------------

class TopicMessagesStrategy(BaseParsingStrategy):
    """
    Авторы сообщений в конкретном топике форума (супергруппа с forum=True).

    Топики реализованы Telegram поверх того же механизма "ответов на
    сообщение", что и комментарии каналов: topic_id — это ID корневого
    сообщения топика (см. ForumTopic.id), и iter_messages(reply_to=topic_id)
    возвращает все сообщения этого топика.
    """

    def __init__(
        self, topic_id: int, limit: int = 5_000, delay: float = 0.5, scan_limit: int = 50_000
    ) -> None:
        super().__init__(limit, delay)
        self.topic_id = topic_id
        self.scan_limit = scan_limit

    async def collect(
        self, client: TelegramClient, entity: Any, source_label: str
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        scanned = 0

        async for msg in client.iter_messages(entity, reply_to=self.topic_id, limit=self.scan_limit):
            if isinstance(msg, MessageService):
                scanned += 1
                continue

            sender = msg.sender
            if isinstance(sender, User):
                parsed = self._from_user(sender, source_label)
                if parsed:
                    users.add(parsed)

            scanned += 1
            if scanned % _PAGE == 0:
                await asyncio.sleep(self.delay)
            if len(users) >= self.limit:
                break

        logger.info("[TopicMessages] %s (topic=%d) → %d users", source_label, self.topic_id, len(users))
        return users


# ---------------------------------------------------------------------------
# LuaStrategySelector — per-entity strategy choice lives in an external,
# hot-reloadable script, instead of one strategy fixed for the whole job.
# ---------------------------------------------------------------------------

_SELECTABLE_STRATEGIES = {
    "members": GroupMembersStrategy,
    "comments": ChannelCommentsStrategy,
    "messages": GroupMessagesStrategy,
    "reactions": ReactionsStrategy,
    "polls": PollsStrategy,
    "system": SystemMessagesStrategy,
}


class LuaStrategySelector:
    """
    Picks a BaseParsingStrategy per entity via a .lua script, for jobs that
    span multiple different sources where one fixed strategy doesn't fit all
    of them. TopicMessagesStrategy is intentionally not selectable here --
    it requires a topic_id the selector has no way to supply.

    Script contract: `return function(entity) return "members" end`, where
    entity = {kind, is_forum, estimated_weight} (kind is one of "chat",
    "supergroup", "channel", "unknown"; see src.extraction.entity_resolver.EntityKind).

    Never raises: a script error or an unknown/unselectable strategy name
    falls back to GroupMembersStrategy(), so a bad script can't derail the
    pipeline -- same principle as LuaScriptFilter (src/extraction/user_filter.py).
    """

    def __init__(self, engine: "LuaEngine", script_name: str) -> None:
        self._engine = engine
        self._script_name = script_name

    def select(self, *, kind: str, is_forum: bool, estimated_weight: float) -> BaseParsingStrategy:
        payload = {"kind": kind, "is_forum": is_forum, "estimated_weight": estimated_weight}
        try:
            name = str(self._engine.call(self._script_name, payload))
        except Exception:
            logger.warning(
                "LuaStrategySelector: script call failed, falling back to GroupMembersStrategy",
                exc_info=True,
            )
            return GroupMembersStrategy()

        strategy_cls = _SELECTABLE_STRATEGIES.get(name)
        if strategy_cls is None:
            logger.warning(
                "LuaStrategySelector: unknown strategy %r from script, falling back to GroupMembersStrategy",
                name,
            )
            return GroupMembersStrategy()
        return strategy_cls()


# ---------------------------------------------------------------------------
# Топики форума: список для выбора topic_id
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ForumTopicInfo:
    id: int
    title: str


async def list_forum_topics(
    client: TelegramClient, entity: Any, limit: int = 100
) -> List[ForumTopicInfo]:
    """
    Список топиков форума (для выбора topic_id перед TopicMessagesStrategy).

    entity должна быть супергруппой с включённым форумом — иначе Telegram
    вернёт ошибку API (не перехватывается здесь, пробрасывается вызывающему).
    """
    result = await client(GetForumTopicsRequest(
        peer=entity,
        offset_date=None,
        offset_id=0,
        offset_topic=0,
        limit=limit,
    ))
    return [
        ForumTopicInfo(id=t.id, title=t.title)
        for t in result.topics
        if isinstance(t, ForumTopic)
    ]


# ---------------------------------------------------------------------------
# FloodWait retry helper (сохранён для обратной совместимости)
# ---------------------------------------------------------------------------

async def _resilient_call(
    coro_factory: Callable[[], Coroutine[Any, Any, Any]],
    policy: TimingPolicy,
    label: str = "call",
) -> Any:
    for attempt in range(1, policy.max_flood_retries + 1):
        try:
            return await coro_factory()
        except FloodWaitError as e:
            wait_time = e.seconds + policy.next_delay()
            logger.warning("[%s] FloodWait attempt %d/%d — sleeping %.1fs",
                           label, attempt, policy.max_flood_retries, wait_time)
            if attempt >= policy.max_flood_retries:
                raise
            await asyncio.sleep(wait_time)
    raise RuntimeError(f"[{label}] Exhausted retries without result.")


# ---------------------------------------------------------------------------
# Новый публичный API: extract_users
# ---------------------------------------------------------------------------

async def extract_users(
    client: TelegramClient,
    entity_identifier: str,
    strategy: BaseParsingStrategy,
    policy: TimingPolicy,
) -> Set[ParsedUser]:
    """
    Собирает ParsedUser из entity_identifier с указанной стратегией.

    entity_identifier — любой формат (@username, t.me/+hash, числовой ID).
    Возвращает пустой set на любую неустранимую ошибку (не бросает).
    """
    resolver = UniversalEntityResolver(client)
    try:
        resolved = await resolver.resolve(entity_identifier)
    except Exception as exc:
        logger.error("Cannot resolve entity '%s': %s", entity_identifier, exc)
        return set()

    try:
        return await strategy.collect(client, resolved.peer, entity_identifier)
    except FloodWaitError:
        logger.error("FloodWait limit exceeded for '%s'. Skipping.", entity_identifier)
        return set()
    except Exception as exc:
        logger.error("Strategy %s failed for '%s': %s",
                     type(strategy).__name__, entity_identifier, exc, exc_info=True)
        return set()


# ---------------------------------------------------------------------------
# Обратная совместимость: extract_members → Set[str] (юзернеймы)
# ---------------------------------------------------------------------------

async def extract_members(
    client: TelegramClient,
    entity_identifier: str,
    policy: TimingPolicy,
    message_limit: int = 1000,
) -> Set[str]:
    """
    Извлекает юзернеймы участников из любой Telegram-сущности.

    Поведение:
      CHANNEL → GroupMessagesStrategy (members list недоступен).
      CHAT / SUPERGROUP → GroupMembersStrategy, фолбэк на GroupMessagesStrategy.

    Возвращает пустой set при любой неустранимой ошибке.
    """
    logger.info("extract_members: target='%s'", entity_identifier)

    resolver = UniversalEntityResolver(client)
    try:
        resolved = await resolver.resolve(entity_identifier)
    except Exception as exc:
        logger.error("Cannot resolve entity '%s': %s", entity_identifier, exc)
        return set()

    msg_strategy = GroupMessagesStrategy(limit=message_limit, delay=policy.next_delay())

    if resolved.kind == EntityKind.CHANNEL:
        logger.info("'%s' is a broadcast Channel — using GroupMessagesStrategy.", entity_identifier)
        try:
            users = await msg_strategy.collect(client, resolved.entity, entity_identifier)
            return {u.username for u in users if u.username}
        except Exception as exc:
            logger.error("GroupMessagesStrategy failed for '%s': %s", entity_identifier, exc)
            return set()

    try:
        members_strategy = GroupMembersStrategy(limit=50_000, delay=policy.next_delay())
        users = await members_strategy.collect(client, resolved.entity, entity_identifier)
        return {u.username for u in users if u.username}

    except (ChatAdminRequiredError, ChannelPrivateError) as exc:
        logger.warning("GroupMembersStrategy blocked by %s for '%s'. Falling back.",
                       type(exc).__name__, entity_identifier)
        try:
            users = await msg_strategy.collect(client, resolved.entity, entity_identifier)
            return {u.username for u in users if u.username}
        except Exception as fallback_exc:
            logger.error("Fallback also failed for '%s': %s", entity_identifier, fallback_exc)
            return set()

    except FloodWaitError:
        logger.error("FloodWait limit exceeded for '%s'. Skipping.", entity_identifier)
        return set()

    except Exception as exc:
        logger.error("Unexpected error extracting from '%s': %s",
                     entity_identifier, exc, exc_info=True)
        return set()
