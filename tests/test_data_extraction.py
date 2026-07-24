"""tests/test_data_extraction.py — TopicMessagesStrategy, list_forum_topics, ParsedUser.bot."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telethon.tl.types import ForumTopic, ForumTopicDeleted, MessageService, User

from src.extraction.data_extraction import (
    ForumTopicInfo,
    ParsedUser,
    TopicMessagesStrategy,
    list_forum_topics,
)

pytestmark = pytest.mark.unit


def make_user(user_id: int, bot: bool = False) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = user_id
    user.username = f"user{user_id}"
    user.first_name = "First"
    user.last_name = "Last"
    user.phone = ""
    user.premium = False
    user.photo = None
    user.bot = bot
    user.status = None
    return user


def make_message(sender) -> MagicMock:
    msg = MagicMock()
    msg.sender = sender
    return msg


def make_service_message() -> MagicMock:
    return MagicMock(spec=MessageService)


def async_iter(items):
    async def _gen():
        for item in items:
            yield item
    return _gen()


class TestTopicMessagesStrategy:
    async def test_collects_senders_from_topic(self):
        client = MagicMock()
        alice = make_user(1)
        bob = make_user(2)
        client.iter_messages = MagicMock(return_value=async_iter([
            make_message(alice), make_message(bob),
        ]))

        strategy = TopicMessagesStrategy(topic_id=42, delay=0.0)
        users = await strategy.collect(client, entity="entity", source_label="forum/topic-42")

        client.iter_messages.assert_called_once_with(
            "entity", reply_to=42, limit=strategy.scan_limit
        )
        assert {u.user_id for u in users} == {1, 2}
        assert all(u.source == "forum/topic-42" for u in users)

    async def test_skips_service_messages(self):
        client = MagicMock()
        alice = make_user(1)
        client.iter_messages = MagicMock(return_value=async_iter([
            make_service_message(), make_message(alice),
        ]))

        strategy = TopicMessagesStrategy(topic_id=7, delay=0.0)
        users = await strategy.collect(client, entity="entity", source_label="src")

        assert {u.user_id for u in users} == {1}

    async def test_respects_limit(self):
        client = MagicMock()
        messages = [make_message(make_user(i)) for i in range(5)]
        client.iter_messages = MagicMock(return_value=async_iter(messages))

        strategy = TopicMessagesStrategy(topic_id=1, limit=2, delay=0.0)
        users = await strategy.collect(client, entity="entity", source_label="src")

        assert len(users) == 2

    async def test_no_sender_or_non_user_sender_is_skipped(self):
        client = MagicMock()
        msg_no_sender = make_message(None)
        client.iter_messages = MagicMock(return_value=async_iter([msg_no_sender]))

        strategy = TopicMessagesStrategy(topic_id=1, delay=0.0)
        users = await strategy.collect(client, entity="entity", source_label="src")

        assert users == set()


class TestListForumTopics:
    async def test_returns_only_real_topics(self):
        client = AsyncMock()
        topic = MagicMock(spec=ForumTopic)
        topic.id = 10
        topic.title = "General"
        deleted = MagicMock(spec=ForumTopicDeleted)
        deleted.id = 99

        result = MagicMock()
        result.topics = [topic, deleted]
        client.return_value = result

        topics = await list_forum_topics(client, entity="entity", limit=50)

        assert topics == [ForumTopicInfo(id=10, title="General")]

    async def test_empty_topics_returns_empty_list(self):
        client = AsyncMock()
        result = MagicMock()
        result.topics = []
        client.return_value = result

        topics = await list_forum_topics(client, entity="entity")

        assert topics == []


class TestParsedUserBotField:
    def test_from_user_captures_bot_flag(self):
        bot_user = make_user(1, bot=True)
        human_user = make_user(2, bot=False)

        parsed_bot = TopicMessagesStrategy._from_user(bot_user, "src")
        parsed_human = TopicMessagesStrategy._from_user(human_user, "src")

        assert parsed_bot.bot is True
        assert parsed_human.bot is False

    def test_default_bot_is_false(self):
        assert ParsedUser(user_id=1).bot is False
