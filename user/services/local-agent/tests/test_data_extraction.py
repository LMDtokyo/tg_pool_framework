"""tests/test_data_extraction.py — TopicMessagesStrategy, list_forum_topics, ParsedUser.bot."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telethon.tl.types import (
    ForumTopic,
    ForumTopicDeleted,
    MessageService,
    ReactionCustomEmoji,
    ReactionEmoji,
    User,
)

from tg_pool.extraction.data_extraction import (
    ChannelCommentsStrategy,
    ForumTopicInfo,
    GroupMembersStrategy,
    GroupMessagesStrategy,
    ParsedUser,
    ReactionsStrategy,
    TopicMessagesStrategy,
    _shard_message_id_range,
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


# ---------------------------------------------------------------------------
# Sharding — multiple accounts covering one entity in parallel
# ---------------------------------------------------------------------------

class TestShardMessageIdRange:
    async def test_no_shard_returns_zero_zero_without_any_api_call(self):
        client = AsyncMock()
        result = await _shard_message_id_range(client, "entity", (0, 1))
        assert result == (0, 0)
        client.get_messages.assert_not_called()

    async def test_splits_id_range_into_contiguous_non_overlapping_shards(self):
        client = AsyncMock()
        latest = MagicMock()
        latest.id = 100
        client.get_messages = AsyncMock(return_value=[latest])

        bounds = [await _shard_message_id_range(client, "entity", (i, 4)) for i in range(4)]
        # Both bounds are exclusive -> the inclusive range is (lo+1, hi-1).
        inclusive = [(lo + 1, hi - 1) for lo, hi in bounds]

        assert inclusive[0][0] == 1
        assert inclusive[-1][1] == 100
        for earlier, later in zip(inclusive, inclusive[1:]):
            assert later[0] == earlier[1] + 1  # contiguous, no gap or overlap

    async def test_no_messages_returns_zero_zero(self):
        client = AsyncMock()
        client.get_messages = AsyncMock(return_value=[])
        assert await _shard_message_id_range(client, "entity", (0, 2)) == (0, 0)

    async def test_more_shards_than_messages_gives_an_empty_range(self):
        client = AsyncMock()
        latest = MagicMock()
        latest.id = 5
        client.get_messages = AsyncMock(return_value=[latest])

        # 10 shards over 5 messages: shard 9 starts past the last message.
        min_id, max_id = await _shard_message_id_range(client, "entity", (9, 10))
        assert min_id == max_id  # id > x and id < x is never true -> excludes everything


class TestGroupMembersStrategySharding:
    async def test_unsharded_call_is_unchanged(self):
        client = MagicMock()
        client.iter_participants = MagicMock(return_value=async_iter([make_user(1)]))

        strategy = GroupMembersStrategy(delay=0.0)
        await strategy.collect(client, entity="entity", source_label="src")

        client.iter_participants.assert_called_once_with("entity", aggressive=False)

    async def test_sharded_call_uses_an_offset_limit_slice(self):
        client = MagicMock()
        probe = MagicMock()
        probe.total = 100
        client.get_participants = AsyncMock(return_value=probe)
        client.iter_participants = MagicMock(return_value=async_iter([]))

        strategy = GroupMembersStrategy(delay=0.0)
        await strategy.collect(client, entity="entity", source_label="src", shard=(1, 4))

        client.iter_participants.assert_called_once_with("entity", aggressive=False, offset=25, limit=25)

    async def test_shard_past_member_count_returns_empty_without_iterating(self):
        client = MagicMock()
        probe = MagicMock()
        probe.total = 5
        client.get_participants = AsyncMock(return_value=probe)
        client.iter_participants = MagicMock(return_value=async_iter([make_user(1)]))

        strategy = GroupMembersStrategy(delay=0.0)
        users = await strategy.collect(client, entity="entity", source_label="src", shard=(9, 10))

        assert users == set()
        client.iter_participants.assert_not_called()


class TestGroupMessagesStrategySharding:
    async def test_unsharded_call_has_no_id_bounds(self):
        client = MagicMock()
        client.iter_messages = MagicMock(return_value=async_iter([make_message(make_user(1))]))

        strategy = GroupMessagesStrategy(delay=0.0)
        await strategy.collect(client, entity="entity", source_label="src")

        client.iter_messages.assert_called_once_with("entity", limit=strategy.scan_limit)

    async def test_sharded_call_adds_min_max_id(self):
        client = MagicMock()
        latest = MagicMock()
        latest.id = 100
        client.get_messages = AsyncMock(return_value=[latest])
        client.iter_messages = MagicMock(return_value=async_iter([]))

        strategy = GroupMessagesStrategy(delay=0.0)
        await strategy.collect(client, entity="entity", source_label="src", shard=(0, 4))

        _, kwargs = client.iter_messages.call_args
        assert kwargs["min_id"] == 0
        assert kwargs["max_id"] == 26


class TestChannelCommentsStrategy:
    @staticmethod
    def _post(post_id: int, has_discussion: bool = True) -> MagicMock:
        post = MagicMock()
        post.id = post_id
        if has_discussion:
            post.replies = MagicMock()
            post.replies.comments = True
        else:
            post.replies = None
        return post

    async def test_skips_posts_without_discussion_enabled(self):
        client = MagicMock()
        client.iter_messages = MagicMock(return_value=async_iter([self._post(1, has_discussion=False)]))

        strategy = ChannelCommentsStrategy(delay=0.0)
        users = await strategy.collect(client, entity="channel", source_label="src")

        assert users == set()

    async def test_resolves_linked_discussion_group_and_collects_commenters(self):
        post = self._post(42)

        discussion_msg = MagicMock()
        discussion_msg.id = 999
        discussion_msg.peer_id = MagicMock()
        discussion_msg.peer_id.channel_id = 555
        discussion_chat = MagicMock()
        discussion_chat.id = 555
        discussion_result = MagicMock()
        discussion_result.messages = [discussion_msg]
        discussion_result.chats = [discussion_chat]

        alice = make_user(1)

        def iter_messages_side_effect(entity, **kwargs):
            if entity == "channel":
                return async_iter([post])
            assert entity is discussion_chat
            assert kwargs["reply_to"] == 999
            return async_iter([make_message(alice)])

        client = MagicMock()
        client.iter_messages = MagicMock(side_effect=iter_messages_side_effect)

        async def fake_get_discussion_message(request):
            return discussion_result

        client.side_effect = fake_get_discussion_message

        strategy = ChannelCommentsStrategy(delay=0.0)
        users = await strategy.collect(client, entity="channel", source_label="src")

        assert {u.user_id for u in users} == {1}

    async def test_post_with_no_matching_discussion_thread_is_skipped(self):
        post = self._post(1)
        empty_discussion = MagicMock()
        empty_discussion.messages = []
        empty_discussion.chats = []

        client = MagicMock()
        client.iter_messages = MagicMock(return_value=async_iter([post]))

        async def fake_get_discussion_message(request):
            return empty_discussion

        client.side_effect = fake_get_discussion_message

        strategy = ChannelCommentsStrategy(delay=0.0)
        users = await strategy.collect(client, entity="channel", source_label="src")

        assert users == set()


class TestReactionsStrategyCustomEmoji:
    @staticmethod
    def _post_with_reaction(post_id: int, reaction_type) -> MagicMock:
        post = MagicMock()
        post.id = post_id
        reaction_count = MagicMock()
        reaction_count.reaction = MagicMock(spec=reaction_type)
        post.reactions = MagicMock()
        post.reactions.results = [reaction_count]
        return post

    async def test_custom_emoji_reactions_are_counted(self):
        post = self._post_with_reaction(1, ReactionCustomEmoji)
        client = MagicMock()
        client.iter_messages = MagicMock(return_value=async_iter([post]))

        reactions_result = MagicMock()
        reactions_result.users = [make_user(7)]
        reactions_result.next_offset = None

        async def fake_call(request):
            return reactions_result

        client.side_effect = fake_call

        strategy = ReactionsStrategy(delay=0.0)
        users = await strategy.collect(client, entity="entity", source_label="src")

        assert {u.user_id for u in users} == {7}

    async def test_standard_emoji_reactions_still_counted(self):
        post = self._post_with_reaction(1, ReactionEmoji)
        client = MagicMock()
        client.iter_messages = MagicMock(return_value=async_iter([post]))

        reactions_result = MagicMock()
        reactions_result.users = [make_user(3)]
        reactions_result.next_offset = None

        async def fake_call(request):
            return reactions_result

        client.side_effect = fake_call

        strategy = ReactionsStrategy(delay=0.0)
        users = await strategy.collect(client, entity="entity", source_label="src")

        assert {u.user_id for u in users} == {3}

    async def test_shard_only_collects_its_share_of_posts(self):
        posts = [self._post_with_reaction(i, ReactionEmoji) for i in range(4)]

        async def fake_call(request):
            result = MagicMock()
            result.users = [make_user(request.id)]
            result.next_offset = None
            return result

        client = MagicMock()
        client.side_effect = fake_call
        client.iter_messages = MagicMock(return_value=async_iter(posts))
        strategy = ReactionsStrategy(delay=0.0)
        shard0_users = await strategy.collect(client, entity="entity", source_label="src", shard=(0, 2))

        client.iter_messages = MagicMock(return_value=async_iter(posts))
        shard1_users = await strategy.collect(client, entity="entity", source_label="src", shard=(1, 2))

        assert {u.user_id for u in shard0_users} == {0, 2}
        assert {u.user_id for u in shard1_users} == {1, 3}
