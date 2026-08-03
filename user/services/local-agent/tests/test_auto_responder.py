"""tests/test_auto_responder.py — Lua-driven auto-responder for inbound messages."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_pool.messaging.auto_responder import AutoResponder
from tg_pool.scripting.lua_engine import LuaEngine

pytestmark = pytest.mark.unit


def make_event(text="hello", sender_id=42, username="bob", is_private=True) -> MagicMock:
    event = MagicMock()
    event.raw_text = text
    event.sender_id = sender_id
    event.is_private = is_private
    event.reply = AsyncMock()
    sender = MagicMock()
    sender.username = username
    event.get_sender = AsyncMock(return_value=sender)
    return event


def make_client() -> MagicMock:
    client = MagicMock()
    client.add_event_handler = MagicMock()
    client.remove_event_handler = MagicMock()
    return client


async def _fire(client: MagicMock, event: MagicMock) -> None:
    """Invoke the handler that attach() registered via add_event_handler."""
    handler = client.add_event_handler.call_args[0][0]
    await handler(event)


async def test_script_returning_text_triggers_reply(tmp_path):
    (tmp_path / "auto_reply.lua").write_text(
        "return function(message) return 'Привет, ' .. message.sender_username .. '!' end",
        encoding="utf-8",
    )
    engine = LuaEngine(str(tmp_path))
    responder = AutoResponder(engine)
    client = make_client()
    responder.attach(client, "+7001")

    event = make_event(username="Bob")
    await _fire(client, event)

    event.reply.assert_called_once_with("Привет, Bob!")


async def test_script_returning_nil_does_not_reply(tmp_path):
    (tmp_path / "auto_reply.lua").write_text(
        "return function(message) return nil end", encoding="utf-8",
    )
    engine = LuaEngine(str(tmp_path))
    responder = AutoResponder(engine)
    client = make_client()
    responder.attach(client, "+7001")

    event = make_event()
    await _fire(client, event)

    event.reply.assert_not_called()


async def test_no_script_loaded_does_not_reply(tmp_path):
    engine = LuaEngine(str(tmp_path))  # empty dir -- no auto_reply.lua
    responder = AutoResponder(engine)
    client = make_client()
    responder.attach(client, "+7001")

    event = make_event()
    await _fire(client, event)

    event.reply.assert_not_called()
    event.get_sender.assert_not_called()  # short-circuits before touching the event


async def test_script_runtime_error_is_swallowed(tmp_path):
    (tmp_path / "auto_reply.lua").write_text(
        "return function(message) return message.nonexistent.deep end",
        encoding="utf-8",
    )
    engine = LuaEngine(str(tmp_path))
    responder = AutoResponder(engine)
    client = make_client()
    responder.attach(client, "+7001")

    event = make_event()
    await _fire(client, event)  # must not raise

    event.reply.assert_not_called()


async def test_message_fields_passed_to_script(tmp_path):
    (tmp_path / "auto_reply.lua").write_text(
        """
        return function(message)
            if message.text == 'ping' and message.is_private then
                return 'pong'
            end
            return nil
        end
        """,
        encoding="utf-8",
    )
    engine = LuaEngine(str(tmp_path))
    responder = AutoResponder(engine)
    client = make_client()
    responder.attach(client, "+7001")

    matching_event = make_event(text="ping", is_private=True)
    other_event = make_event(text="something else", is_private=True)
    await _fire(client, matching_event)
    await _fire(client, other_event)

    matching_event.reply.assert_called_once_with("pong")
    other_event.reply.assert_not_called()


async def test_detach_all_removes_every_handler():
    engine = LuaEngine("/does/not/exist")
    responder = AutoResponder(engine)
    client1, client2 = make_client(), make_client()
    responder.attach(client1, "+7001")
    responder.attach(client2, "+7002")

    responder.detach_all()

    client1.remove_event_handler.assert_called_once()
    client2.remove_event_handler.assert_called_once()
