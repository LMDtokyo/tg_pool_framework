"""
src/data_extraction.py — Data Extraction Module.

Паттерн Strategy для сбора пользователей из различных источников Telegram.

Стратегии:
  GroupMembersStrategy    — iter_participants (полный список участников)
  ChannelCommentsStrategy — комментарии к постам через привязанную группу обсуждений
  GroupMessagesStrategy   — авторы сообщений из истории чата
  ReactionsStrategy       — пользователи, оставившие реакции (включая кастомные эмодзи)
  PollsStrategy           — проголосовавшие в опросах
  SystemMessagesStrategy  — служебные события (вход/добавление в чат)
  TopicMessagesStrategy   — авторы сообщений в конкретном топике форума

list_forum_topics() возвращает список топиков форума (для выбора topic_id).

Все стратегии возвращают Set[ParsedUser], дедуплицируя по user_id.

Шардинг (Shard = (index, total)): каждая стратегия умеет собрать только свою
1/total часть entity, так что при parsing одной-единственной цели (не только
при нескольких источниках) весь пул аккаунтов работает параллельно, а не
простаивает — см. orchestrate_extraction_only() в src/orchestrator.py.

Обратная совместимость:
  extract_members() сохраняет прежнюю сигнатуру → Set[str] (юзернеймы).
  Новый API extract_users() возвращает Set[ParsedUser] с полными метаданными.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine, List, Optional, Set, Tuple

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    FloodWaitError,
)
from telethon.tl.functions.messages import (
    GetDiscussionMessageRequest,
    GetForumTopicsRequest,
    GetMessageReactionsListRequest,
    GetPollVotesRequest,
)
from telethon.tl.types import (
    ForumTopic,
    MessageActionChatAddUser,
    MessageActionChatJoinedByLink,
    MessageService,
    ReactionCustomEmoji,
    ReactionEmoji,
    User,
)

from src.config import TimingPolicy
from src.extraction.entity_resolver import EntityKind, UniversalEntityResolver

if TYPE_CHECKING:
    from src.scripting.lua_engine import LuaEngine

logger = logging.getLogger(__name__)

_PAGE = 200

# A strategy's shard is (my_index, total_shards): "I am worker my_index of
# total_shards, collectively covering the whole entity." (0, 1) -- the
# default everywhere -- means "no sharding, I do the whole thing myself",
# which is exactly today's single-account behavior.
Shard = Tuple[int, int]
NO_SHARD: Shard = (0, 1)


async def _shard_message_id_range(
    client: TelegramClient,
    entity: Any,
    shard: Shard,
    *,
    reply_to: Optional[int] = None,
) -> Tuple[int, int]:
    """
    Splits an entity's message-id space into `total` contiguous, non-overlapping
    slices and returns the (min_id, max_id) Telethon bounds (both exclusive) for
    slice `index` -- so N accounts each scan a disjoint fraction of the history
    instead of every account re-reading everything. reply_to narrows this to a
    topic's/discussion's own id space when given.

    Returns (0, 0) -- Telethon's "no bound" sentinel on both ends -- when
    shard is NO_SHARD, or when the id space can't be determined.
    """
    index, total = shard
    if total <= 1:
        return 0, 0

    kwargs = {"reply_to": reply_to} if reply_to is not None else {}
    latest = await client.get_messages(entity, limit=1, **kwargs)
    if not latest or latest[0].id <= 0:
        return 0, 0

    highest_id = latest[0].id
    chunk = -(-highest_id // total)  # ceil division
    lo = index * chunk + 1
    hi = min((index + 1) * chunk, highest_id)
    if lo > hi:
        # More shards than messages: this shard's slice is empty. Both bounds
        # equal to the same id excludes every message (id > x and id < x is
        # never true), which is a clean way to say "nothing for me here"
        # without every caller needing its own empty-range special case.
        return highest_id + 1, highest_id + 1
    return lo - 1, hi + 1


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
        shard: Shard = NO_SHARD,
    ) -> Set[ParsedUser]:
        """
        Собрать участников из entity и вернуть их как set (дедуп по ID).

        shard=(index, total) — если total > 1, собрать только свою часть
        (1/total) данных entity: несколько аккаунтов параллельно покрывают
        одну и ту же entity вместо простоя лишних воркеров при единственном
        источнике. NO_SHARD (по умолчанию) — вся entity целиком, как раньше.
        """

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
        self, client: TelegramClient, entity: Any, source_label: str, shard: Shard = NO_SHARD
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        kwargs: dict = {"aggressive": False}

        index, total = shard
        if total > 1:
            # get_participants(limit=1) still populates .total from the API's
            # count field, so this is a cheap way to learn the member count
            # before deciding this shard's offset/limit slice.
            probe = await client.get_participants(entity, limit=1)
            member_count = getattr(probe, "total", 0) or 0
            if member_count <= 0:
                return users
            chunk = -(-member_count // total)  # ceil division
            offset = index * chunk
            if offset >= member_count:
                return users
            kwargs["offset"] = offset
            kwargs["limit"] = chunk

        async for raw in client.iter_participants(entity, **kwargs):
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
    """
    Читает комментарии к постам канала.

    Комментарии к посту broadcast-канала физически живут не в самом канале, а
    в привязанной к нему группе обсуждений (discussion group) — публикация
    поста автоматически копирует его туда, и "комментарии" — это replies к
    этой копии. GetDiscussionMessageRequest(peer=канал, msg_id=post.id)
    находит эту копию (и саму группу обсуждений в .chats), после чего
    комментарии читаются обычным iter_messages(discussion_group, reply_to=...).
    post.replies.comments=True маркирует посты, у которых обсуждение вообще
    включено — остальные пропускаются без единого лишнего запроса.
    """

    def __init__(self, limit: int = 5_000, delay: float = 0.5, max_posts: int = 50) -> None:
        super().__init__(limit, delay)
        self.max_posts = max_posts

    async def collect(
        self, client: TelegramClient, entity: Any, source_label: str, shard: Shard = NO_SHARD
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        index, total = shard
        post_index = 0

        async for post in client.iter_messages(entity, limit=self.max_posts):
            if len(users) >= self.limit:
                break

            my_turn = total <= 1 or post_index % total == index
            post_index += 1
            if not my_turn:
                continue

            if not post.replies or not post.replies.comments:
                continue

            try:
                discussion = await client(GetDiscussionMessageRequest(peer=entity, msg_id=post.id))
            except Exception as exc:
                logger.debug("[ChannelComments] no discussion thread for post %d: %s", post.id, exc)
                continue
            if not discussion.messages or not discussion.chats:
                continue

            root_id = discussion.messages[0].id
            discussion_channel_id = getattr(discussion.messages[0].peer_id, "channel_id", None)
            discussion_peer = next(
                (chat for chat in discussion.chats if getattr(chat, "id", None) == discussion_channel_id),
                discussion.chats[0],
            )

            async for comment in client.iter_messages(discussion_peer, reply_to=root_id):
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
        self, client: TelegramClient, entity: Any, source_label: str, shard: Shard = NO_SHARD
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        scanned = 0

        kwargs: dict = {"limit": self.scan_limit}
        if shard[1] > 1:
            min_id, max_id = await _shard_message_id_range(client, entity, shard)
            kwargs["min_id"] = min_id
            kwargs["max_id"] = max_id

        async for msg in client.iter_messages(entity, **kwargs):
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
        self, client: TelegramClient, entity: Any, source_label: str, shard: Shard = NO_SHARD
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        posts_checked = 0
        index, total = shard

        async for post in client.iter_messages(entity, limit=self.max_posts):
            if posts_checked >= self.max_posts or len(users) >= self.limit:
                break
            my_turn = total <= 1 or posts_checked % total == index
            posts_checked += 1
            if not my_turn:
                continue

            if not post.reactions:
                continue

            for rc in post.reactions.results:
                # ReactionCustomEmoji (Premium custom-emoji reactions) counts
                # too -- only ReactionPaid (Telegram Stars) has no reactor list.
                if not isinstance(rc.reaction, (ReactionEmoji, ReactionCustomEmoji)):
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
        self, client: TelegramClient, entity: Any, source_label: str, shard: Shard = NO_SHARD
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        polls_found = 0
        index, total = shard

        async for msg in client.iter_messages(entity, limit=200):
            if polls_found >= self.max_polls or len(users) >= self.limit:
                break

            media = getattr(msg, "media", None)
            if media is None or not hasattr(media, "poll"):
                continue

            my_turn = total <= 1 or polls_found % total == index
            polls_found += 1
            if not my_turn:
                continue
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
        self, client: TelegramClient, entity: Any, source_label: str, shard: Shard = NO_SHARD
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        seen_ids: Set[int] = set()
        scanned = 0

        kwargs: dict = {"limit": self.limit * 5}
        if shard[1] > 1:
            min_id, max_id = await _shard_message_id_range(client, entity, shard)
            kwargs["min_id"] = min_id
            kwargs["max_id"] = max_id

        async for msg in client.iter_messages(entity, **kwargs):
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
        self, client: TelegramClient, entity: Any, source_label: str, shard: Shard = NO_SHARD
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        scanned = 0

        kwargs: dict = {"reply_to": self.topic_id, "limit": self.scan_limit}
        if shard[1] > 1:
            min_id, max_id = await _shard_message_id_range(client, entity, shard, reply_to=self.topic_id)
            kwargs["min_id"] = min_id
            kwargs["max_id"] = max_id

        async for msg in client.iter_messages(entity, **kwargs):
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

    def select(
        self, *, kind: str, is_forum: bool, estimated_weight: float, has_discussion: bool = False
    ) -> BaseParsingStrategy:
        payload = {
            "kind": kind,
            "is_forum": is_forum,
            "estimated_weight": estimated_weight,
            "has_discussion": has_discussion,
        }
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


class CompositeStrategy(BaseParsingStrategy):
    """
    Runs several strategies over the same entity and unions their results.

    Used by AutoStrategySelector for anything that isn't a broadcast channel:
    a group's member list alone badly undercounts when the group has
    restricted/"hidden" member visibility (a real, common Telegram group
    privacy setting) -- iter_participants then only returns a handful of
    people (admins + a few "shown" members) to a non-admin account, no matter
    how many members the group actually has. Message authors, reactors, poll
    voters, and join-service-message senders are still fully readable through
    the regular message-history API regardless of that setting, and often
    surface users the member list hides entirely -- so instead of picking one
    source, auto mode combines all of them and merges by user_id.

    Each sub-strategy receives the same shard, so sharding still spreads work
    across the whole worker pool -- shard (i, n) means "collect my 1/n slice
    of every sub-strategy", not "run 1/n of the sub-strategies". A
    sub-strategy that errors (e.g. ChatAdminRequiredError from a
    permission-restricted member list) is logged and skipped rather than
    failing the whole entity.
    """

    def __init__(self, strategies: List[BaseParsingStrategy], limit: int = 5_000) -> None:
        super().__init__(limit=limit)
        self._strategies = strategies

    async def collect(
        self, client: TelegramClient, entity: Any, source_label: str, shard: Shard = NO_SHARD
    ) -> Set[ParsedUser]:
        users: Set[ParsedUser] = set()
        for strategy in self._strategies:
            if len(users) >= self.limit:
                break
            try:
                found = await strategy.collect(client, entity, source_label, shard)
            except Exception as exc:
                logger.warning(
                    "[Composite] %s failed for %s, skipping: %s",
                    type(strategy).__name__, source_label, exc,
                )
                continue
            users |= found
        logger.info(
            "[Composite] %s → %d users (%d sub-strategies)",
            source_label, len(users), len(self._strategies),
        )
        return users


class AutoStrategySelector:
    """
    "Умный" (smart) режим: выбирает стратегию (или комбинацию стратегий) под
    каждую entity сама, без Lua-скрипта — обычная эвристика на сигналах из
    EntityInfo. Тот же интерфейс, что у LuaStrategySelector (duck typing:
    _collect_bucket не знает, какой из двух ему подсунули, и не отличает
    CompositeStrategy от одиночной).

    Эвристика:
      channel                        → reactions + polls + members (лучший
        случай) + comments, если включены обсуждения — объединённые.
        Broadcast-посты не имеют авторов-пользователей и join-событий
        (GroupMessages/SystemMessages тут в принципе не применимы —
        отправитель поста это сам канал, а не User), но реакции и опросы
        есть почти всегда, а список подписчиков иногда виден и не-админам.
        GroupMembersStrategy пробуется всегда: закрытый список (обычный
        случай) просто отбрасывается CompositeStrategy без вреда остальным
        источникам, а там где он открыт — это огромная прибавка к охвату.
      chat / supergroup / forum /
        unknown                      → members + messages + reactions +
        polls + system, объединённые — список участников у многих групп
        ограничен приватностью ("скрытые участники" в настройках группы) и
        показывает не-админу лишь горстку людей независимо от реального
        размера группы, тогда как авторы сообщений, реагирующие,
        проголосовавшие и вошедшие по сервисным сообщениям остаются
        полностью читаемыми и часто перекрывают то, что список участников
        скрывает.
    """

    def select(
        self, *, kind: str, is_forum: bool, estimated_weight: float, has_discussion: bool = False
    ) -> BaseParsingStrategy:
        if kind == "channel":
            strategies: List[BaseParsingStrategy] = [
                ReactionsStrategy(), PollsStrategy(), GroupMembersStrategy(),
            ]
            if has_discussion:
                strategies.append(ChannelCommentsStrategy())
            return CompositeStrategy(strategies)

        return CompositeStrategy([
            GroupMembersStrategy(),
            GroupMessagesStrategy(),
            ReactionsStrategy(),
            PollsStrategy(),
            SystemMessagesStrategy(),
        ])


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
    shard: Shard = NO_SHARD,
) -> Set[ParsedUser]:
    """
    Собирает ParsedUser из entity_identifier с указанной стратегией.

    entity_identifier — любой формат (@username, t.me/+hash, числовой ID).
    shard — см. BaseParsingStrategy.collect(): (0, 1) означает "вся entity
    одним аккаунтом", как раньше; при total > 1 несколько аккаунтов
    параллельно покрывают одну и ту же entity.
    Возвращает пустой set на любую неустранимую ошибку (не бросает).
    """
    resolver = UniversalEntityResolver(client)
    try:
        resolved = await resolver.resolve(entity_identifier)
    except Exception as exc:
        logger.error("Cannot resolve entity '%s': %s", entity_identifier, exc)
        return set()

    try:
        return await strategy.collect(client, resolved.peer, entity_identifier, shard=shard)
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
