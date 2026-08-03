"""tests/test_auto_strategy_selector.py — tg_pool/extraction/data_extraction.py::AutoStrategySelector, CompositeStrategy."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tg_pool.extraction.data_extraction import (
    AutoStrategySelector,
    ChannelCommentsStrategy,
    CompositeStrategy,
    GroupMembersStrategy,
    GroupMessagesStrategy,
    ParsedUser,
    PollsStrategy,
    ReactionsStrategy,
    SystemMessagesStrategy,
)

pytestmark = pytest.mark.unit


class TestAutoStrategySelector:
    def test_channel_with_discussion_combines_reactions_polls_members_and_comments(self):
        selector = AutoStrategySelector()
        strategy = selector.select(
            kind="channel", is_forum=False, estimated_weight=100.0, has_discussion=True,
        )
        assert isinstance(strategy, CompositeStrategy)
        kinds = {type(s) for s in strategy._strategies}
        assert kinds == {ReactionsStrategy, PollsStrategy, GroupMembersStrategy, ChannelCommentsStrategy}

    def test_channel_without_discussion_combines_reactions_polls_and_members(self):
        selector = AutoStrategySelector()
        strategy = selector.select(
            kind="channel", is_forum=False, estimated_weight=100.0, has_discussion=False,
        )
        assert isinstance(strategy, CompositeStrategy)
        kinds = {type(s) for s in strategy._strategies}
        assert kinds == {ReactionsStrategy, PollsStrategy, GroupMembersStrategy}

    def test_channel_defaults_to_no_comments_when_has_discussion_omitted(self):
        selector = AutoStrategySelector()
        strategy = selector.select(kind="channel", is_forum=False, estimated_weight=100.0)
        assert isinstance(strategy, CompositeStrategy)
        kinds = {type(s) for s in strategy._strategies}
        assert ChannelCommentsStrategy not in kinds

    def test_chat_combines_every_general_purpose_strategy(self):
        selector = AutoStrategySelector()
        strategy = selector.select(kind="chat", is_forum=False, estimated_weight=50.0)
        assert isinstance(strategy, CompositeStrategy)
        kinds = {type(s) for s in strategy._strategies}
        assert kinds == {
            GroupMembersStrategy, GroupMessagesStrategy, ReactionsStrategy,
            PollsStrategy, SystemMessagesStrategy,
        }

    def test_supergroup_combines_every_general_purpose_strategy(self):
        selector = AutoStrategySelector()
        strategy = selector.select(kind="supergroup", is_forum=False, estimated_weight=50.0)
        assert isinstance(strategy, CompositeStrategy)

    def test_forum_supergroup_combines_every_general_purpose_strategy(self):
        selector = AutoStrategySelector()
        strategy = selector.select(kind="supergroup", is_forum=True, estimated_weight=50.0)
        assert isinstance(strategy, CompositeStrategy)

    def test_unknown_kind_falls_back_to_composite(self):
        selector = AutoStrategySelector()
        strategy = selector.select(kind="unknown", is_forum=False, estimated_weight=1.0)
        assert isinstance(strategy, CompositeStrategy)


class TestCompositeStrategy:
    async def test_merges_results_from_every_sub_strategy(self):
        members = AsyncMock(return_value={ParsedUser(user_id=1), ParsedUser(user_id=2)})
        reactions = AsyncMock(return_value={ParsedUser(user_id=2), ParsedUser(user_id=3)})
        sub_a = AsyncMock()
        sub_a.collect = members
        sub_b = AsyncMock()
        sub_b.collect = reactions

        composite = CompositeStrategy([sub_a, sub_b])
        users = await composite.collect(client=object(), entity=object(), source_label="@group")

        assert {u.user_id for u in users} == {1, 2, 3}

    async def test_skips_a_sub_strategy_that_raises(self):
        broken = AsyncMock()
        broken.collect = AsyncMock(side_effect=RuntimeError("ChatAdminRequiredError"))
        working = AsyncMock()
        working.collect = AsyncMock(return_value={ParsedUser(user_id=5)})

        composite = CompositeStrategy([broken, working])
        users = await composite.collect(client=object(), entity=object(), source_label="@group")

        assert {u.user_id for u in users} == {5}

    async def test_passes_through_client_entity_label_and_shard(self):
        sub = AsyncMock()
        sub.collect = AsyncMock(return_value=set())
        client, entity = object(), object()

        composite = CompositeStrategy([sub])
        await composite.collect(client, entity, "@group", shard=(1, 3))

        sub.collect.assert_awaited_once_with(client, entity, "@group", (1, 3))

    async def test_stops_early_once_limit_reached(self):
        sub_a = AsyncMock()
        sub_a.collect = AsyncMock(return_value={ParsedUser(user_id=i) for i in range(3)})
        sub_b = AsyncMock()
        sub_b.collect = AsyncMock(return_value={ParsedUser(user_id=99)})

        composite = CompositeStrategy([sub_a, sub_b], limit=2)
        users = await composite.collect(client=object(), entity=object(), source_label="@group")

        assert len(users) == 3  # sub_a alone already exceeds the limit
        sub_b.collect.assert_not_awaited()
