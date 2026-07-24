"""
src/messaging/auto_responder.py — Lua-driven auto-reply to inbound messages.

New pattern for the project: event-driven listening (Telethon's NewMessage
event) rather than polling (health_checker.py polls @SpamBot via get_messages).
Reuses LuaEngine so reply logic is hot-reloadable without a process restart —
same script contract as LuaScriptFilter (src/extraction/user_filter.py):
`return function(...) ... end`.

Lives on top of ClientPool's existing connect/disconnect lifecycle rather than
a separate long-running "listen" mode: attach() is called once per active
worker right after Phase 0 (see orchestrator.py), detach_all() in Phase 4
cleanup. The auto-responder is therefore only active for the duration of the
current send campaign — a standalone "listen only" entry point is a possible
future addition, not built here.
"""

from __future__ import annotations

import logging
from typing import Dict, Tuple

from telethon import TelegramClient, events

from src.scripting.lua_engine import LuaEngine

logger = logging.getLogger(__name__)


class AutoResponder:
    """
    Attaches a NewMessage(incoming=True) handler to each client that consults
    a Lua script to decide whether/how to reply.

    Script contract: `return function(message) return reply_text_or_nil end`,
    where `message` is a table with: text, sender_id, sender_username, is_private.
    Any script error (compile-time or at call time) is logged and swallowed —
    one broken rule must not take down the inbound handler.
    """

    def __init__(self, engine: LuaEngine, script_name: str = "auto_reply") -> None:
        self._engine = engine
        self._script_name = script_name
        self._handlers: Dict[str, Tuple[TelegramClient, object]] = {}

    def attach(self, client: TelegramClient, phone: str) -> None:
        async def _handler(event: "events.NewMessage.Event") -> None:
            if not self._engine.has_script(self._script_name):
                return

            try:
                sender = await event.get_sender()
                message = {
                    "text": event.raw_text or "",
                    "sender_id": event.sender_id or 0,
                    "sender_username": getattr(sender, "username", "") or "",
                    "is_private": bool(event.is_private),
                }
                reply = self._engine.call(self._script_name, message)
            except Exception:
                logger.exception("AutoResponder[%s]: script error, skipping reply", phone)
                return

            if reply:
                await event.reply(str(reply))

        client.add_event_handler(_handler, events.NewMessage(incoming=True))
        self._handlers[phone] = (client, _handler)
        logger.info("AutoResponder: attached to %s", phone)

    def detach_all(self) -> None:
        for phone, (client, handler) in self._handlers.items():
            client.remove_event_handler(handler, events.NewMessage)
            logger.info("AutoResponder: detached from %s", phone)
        self._handlers.clear()
