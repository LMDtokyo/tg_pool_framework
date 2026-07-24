"""
src/messaging/forward_source.py — Resolves a "repost this existing message"
source for a campaign send: either a t.me link to a specific channel post, or
a bot/channel username plus a pool of message IDs to forward from (one chosen
per recipient).

Link parsing needs no network round-trip: Telethon's forward_messages()
accepts a username string or a numeric chat ID directly as from_peer and
resolves it internally, so a plain regex match is enough on our side.
"""

from __future__ import annotations

import random
import re
from typing import List, Optional, Tuple, Union

# Public channel/bot post: t.me/name/123 (deliberately excludes /c/ private links)
_PUBLIC_MSG_LINK_RE = re.compile(r"(?:https?://)?t\.me/(?!c/)([A-Za-z0-9_]+)/(\d+)")

# Private channel post: t.me/c/<internal_id>/<msg_id> -- internal_id needs the
# -100 prefix Telegram's client apps add internally to make a real chat ID.
_PRIVATE_MSG_LINK_RE = re.compile(r"(?:https?://)?t\.me/c/(\d+)/(\d+)")


def parse_message_link(link: str) -> Optional[Tuple[Union[str, int], int]]:
    """
    Parses a t.me message link into (peer, message_id), or None if it doesn't
    look like one. peer is a username string for public links, or a signed
    int chat ID for private (/c/) links.
    """
    link = link.strip()

    match = _PRIVATE_MSG_LINK_RE.search(link)
    if match:
        internal_id, message_id = match.groups()
        return int(f"-100{internal_id}"), int(message_id)

    match = _PUBLIC_MSG_LINK_RE.search(link)
    if match:
        username, message_id = match.groups()
        return username, int(message_id)

    return None


def resolve_forward_source(
    forward_link: Optional[str],
    bot_relay_username: Optional[str],
    bot_relay_message_ids: Optional[List[int]],
    rng: Optional[random.Random] = None,
) -> Optional[Tuple[Union[str, int], int]]:
    """
    Returns (peer, message_id) to forward, preferring an explicit forward_link
    over the bot-relay pool. None if neither source is configured/parseable.
    """
    if forward_link:
        parsed = parse_message_link(forward_link)
        if parsed is not None:
            return parsed

    if bot_relay_username and bot_relay_message_ids:
        chooser = rng.choice if rng is not None else random.choice
        peer = bot_relay_username.lstrip("@")
        return peer, chooser(bot_relay_message_ids)

    return None
