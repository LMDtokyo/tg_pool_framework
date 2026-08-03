"""tests/test_lua_strategy_selector.py — tg_pool/extraction/data_extraction.py::LuaStrategySelector."""

from __future__ import annotations

import pytest

from tg_pool.extraction.data_extraction import (
    ChannelCommentsStrategy,
    GroupMembersStrategy,
    GroupMessagesStrategy,
    LuaStrategySelector,
    PollsStrategy,
    ReactionsStrategy,
    SystemMessagesStrategy,
)
from tg_pool.scripting.lua_engine import LuaEngine

pytestmark = pytest.mark.unit


def _write_script(tmp_path, name: str, body: str):
    (tmp_path / f"{name}.lua").write_text(body, encoding="utf-8")
    return LuaEngine(str(tmp_path))


class TestLuaStrategySelector:
    def test_selects_strategy_named_by_script(self, tmp_path):
        engine = _write_script(
            tmp_path, "pick",
            "return function(entity) return 'comments' end",
        )
        selector = LuaStrategySelector(engine, "pick")

        strategy = selector.select(kind="channel", is_forum=False, estimated_weight=100.0)

        assert isinstance(strategy, ChannelCommentsStrategy)

    def test_script_can_branch_on_entity_fields(self, tmp_path):
        engine = _write_script(
            tmp_path, "branch",
            """
            return function(entity)
                if entity.is_forum then
                    return 'system'
                end
                if entity.estimated_weight > 1000 then
                    return 'reactions'
                end
                return 'members'
            end
            """,
        )
        selector = LuaStrategySelector(engine, "branch")

        assert isinstance(
            selector.select(kind="supergroup", is_forum=True, estimated_weight=5.0),
            SystemMessagesStrategy,
        )
        assert isinstance(
            selector.select(kind="supergroup", is_forum=False, estimated_weight=5000.0),
            ReactionsStrategy,
        )
        assert isinstance(
            selector.select(kind="chat", is_forum=False, estimated_weight=5.0),
            GroupMembersStrategy,
        )

    def test_all_selectable_strategy_names_resolve(self, tmp_path):
        expected = {
            "members": GroupMembersStrategy,
            "comments": ChannelCommentsStrategy,
            "messages": GroupMessagesStrategy,
            "reactions": ReactionsStrategy,
            "polls": PollsStrategy,
            "system": SystemMessagesStrategy,
        }
        for name, cls in expected.items():
            engine = _write_script(tmp_path, f"select_{name}", f"return function(e) return '{name}' end")
            selector = LuaStrategySelector(engine, f"select_{name}")
            assert isinstance(
                selector.select(kind="chat", is_forum=False, estimated_weight=1.0), cls
            )

    def test_unknown_strategy_name_falls_back_to_members(self, tmp_path):
        engine = _write_script(
            tmp_path, "bogus",
            "return function(entity) return 'nonsense' end",
        )
        selector = LuaStrategySelector(engine, "bogus")

        strategy = selector.select(kind="chat", is_forum=False, estimated_weight=1.0)

        assert isinstance(strategy, GroupMembersStrategy)

    def test_topic_is_not_a_selectable_strategy(self, tmp_path):
        engine = _write_script(
            tmp_path, "wants_topic",
            "return function(entity) return 'topic' end",
        )
        selector = LuaStrategySelector(engine, "wants_topic")

        strategy = selector.select(kind="supergroup", is_forum=True, estimated_weight=1.0)

        assert isinstance(strategy, GroupMembersStrategy)

    def test_script_error_falls_back_to_members(self, tmp_path):
        engine = _write_script(
            tmp_path, "broken",
            "return function(entity) error('boom') end",
        )
        selector = LuaStrategySelector(engine, "broken")

        strategy = selector.select(kind="chat", is_forum=False, estimated_weight=1.0)

        assert isinstance(strategy, GroupMembersStrategy)
