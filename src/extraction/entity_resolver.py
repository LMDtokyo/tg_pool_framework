"""
src/entity_resolver.py — Universal Entity Resolver.

Handles every Telegram identifier format:
  - @username / plain username
  - t.me/username      (public link)
  - t.me/joinchat/HASH (private invite, legacy format)
  - t.me/+HASH         (private invite, current format)
  - Raw integer chat ID

Auto-joins private chats if the account is not yet a member.
Classifies the resolved entity so callers can choose the right strategy.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Optional

from telethon import TelegramClient
from telethon.errors import (
    InviteHashExpiredError,
    InviteHashInvalidError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import (
    CheckChatInviteRequest,
    ImportChatInviteRequest,
)
from telethon.tl.types import Channel, Chat, ChatInviteAlready, ChatInvitePeek

logger = logging.getLogger(__name__)

_INVITE_RE = re.compile(r"(?:t\.me/joinchat/|t\.me/\+)([A-Za-z0-9_-]+)")
_PUBLIC_RE = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]+)")


class EntityKind(Enum):
    CHAT = auto()        # Regular group (Chat)
    SUPERGROUP = auto()  # Channel with megagroup=True
    CHANNEL = auto()     # Broadcast channel — members list hidden by default
    UNKNOWN = auto()


@dataclass
class ResolvedEntity:
    peer: Any          # InputPeer for API calls
    entity: Any        # Full TL object (Channel / Chat / ...)
    kind: EntityKind
    title: str = ""


def _classify(entity: Any) -> EntityKind:
    if isinstance(entity, Channel):
        return EntityKind.SUPERGROUP if entity.megagroup else EntityKind.CHANNEL
    if isinstance(entity, Chat):
        return EntityKind.CHAT
    return EntityKind.UNKNOWN


def _parse_invite_hash(text: str) -> Optional[str]:
    m = _INVITE_RE.search(text)
    return m.group(1) if m else None


def _parse_public_username(text: str) -> Optional[str]:
    m = _PUBLIC_RE.search(text)
    return m.group(1) if m else None


class UniversalEntityResolver:
    """
    Resolves any Telegram identifier to a typed ResolvedEntity.

    One instance per TelegramClient. Stateless between calls — safe to
    reuse for multiple resolve() invocations on the same client.
    """

    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    async def resolve(self, identifier: str) -> ResolvedEntity:
        """
        Entry point. Dispatches to the correct resolution path.

        Resolution order:
          1. Private invite hash  → _resolve_invite()
          2. Public t.me link     → _resolve_public(username)
          3. @username            → _resolve_public(username without @)
          4. Raw integer ID       → _resolve_public(int)
          5. Anything else        → _resolve_public(as-is)
        """
        identifier = identifier.strip()

        invite_hash = _parse_invite_hash(identifier)
        if invite_hash:
            return await self._resolve_invite(invite_hash)

        public_username = _parse_public_username(identifier)
        if public_username:
            return await self._resolve_public(public_username)

        if identifier.startswith("@"):
            return await self._resolve_public(identifier[1:])

        try:
            return await self._resolve_public(int(identifier))
        except ValueError:
            pass

        return await self._resolve_public(identifier)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _resolve_invite(self, hash_: str) -> ResolvedEntity:
        """
        Handles private invite links.

        Flow:
          1. CheckChatInviteRequest → inspect result type.
          2. ChatInviteAlready / ChatInvitePeek → already a member.
          3. Any other type → ImportChatInviteRequest to join first.
          4. Build ResolvedEntity from the joined chat object.
        """
        logger.info("Resolving private invite hash %s...", hash_[:8])

        try:
            invite = await self._client(CheckChatInviteRequest(hash=hash_))
        except InviteHashInvalidError:
            raise ValueError(f"Invite hash '{hash_}' is invalid.")
        except InviteHashExpiredError:
            raise ValueError(f"Invite hash '{hash_}' has expired.")

        if isinstance(invite, (ChatInviteAlready, ChatInvitePeek)):
            chat = invite.chat
            logger.info("Already a member of '%s'.", getattr(chat, "title", "?"))
        else:
            title = getattr(invite, "title", "?")
            logger.info("Not a member of '%s'. Joining...", title)
            try:
                result = await self._client(ImportChatInviteRequest(hash=hash_))
                chats = getattr(result, "chats", [])
                if not chats:
                    raise RuntimeError("ImportChatInviteRequest returned no chat.")
                chat = chats[0]
                logger.info("Joined '%s'.", getattr(chat, "title", "?"))
            except UserAlreadyParticipantError:
                # Race: concurrent worker already joined
                logger.warning("UserAlreadyParticipantError — joined concurrently.")
                invite = await self._client(CheckChatInviteRequest(hash=hash_))
                chat = invite.chat

        kind = _classify(chat)
        return ResolvedEntity(
            peer=await self._client.get_input_entity(chat),
            entity=chat,
            kind=kind,
            title=getattr(chat, "title", ""),
        )

    async def _resolve_public(self, identifier: Any) -> ResolvedEntity:
        """Resolves @username, plain username, or integer ID."""
        entity = await self._client.get_entity(identifier)
        kind = _classify(entity)
        label = getattr(entity, "title", getattr(entity, "username", str(identifier)))
        logger.info("Resolved '%s' → %s (kind=%s)", identifier, label, kind.name)
        return ResolvedEntity(
            peer=await self._client.get_input_entity(entity),
            entity=entity,
            kind=kind,
            title=getattr(entity, "title", ""),
        )


@dataclass
class EntityInfo:
    """
    Cheap per-entity metadata gathered from a single resolve() call — feeds
    both LPT work distribution (weight) and Lua-based per-entity strategy
    selection (kind/is_forum). Falls back to a safe default
    (weight=1.0, kind=UNKNOWN, is_forum=False) on any resolution failure,
    so a bad lookup can't derail the pipeline -- same principle as
    src.accounts.geo.country_for_phone().
    """
    weight: float = 1.0
    kind: EntityKind = EntityKind.UNKNOWN
    is_forum: bool = False


async def describe_entity(client: TelegramClient, identifier: str) -> EntityInfo:
    """Resolves identifier once and reports its size/kind/forum-ness. Never raises."""
    try:
        resolved = await UniversalEntityResolver(client).resolve(identifier)
        is_forum = bool(getattr(resolved.entity, "forum", False))

        if resolved.kind in (EntityKind.SUPERGROUP, EntityKind.CHANNEL):
            full = await client(GetFullChannelRequest(resolved.peer))
            count = full.full_chat.participants_count
        elif resolved.kind is EntityKind.CHAT:
            count = resolved.entity.participants_count
        else:
            return EntityInfo(weight=1.0, kind=resolved.kind, is_forum=is_forum)

        weight = float(count) if count else 1.0
        return EntityInfo(weight=weight, kind=resolved.kind, is_forum=is_forum)
    except Exception:
        logger.warning("describe_entity(%s) failed, falling back to defaults", identifier, exc_info=True)
        return EntityInfo()


async def estimate_entity_weight(client: TelegramClient, identifier: str) -> float:
    """
    Cheap estimate of an entity's size, for weighting work distribution
    (see src.orchestrator._distribute_by_weight). Never raises.
    """
    return (await describe_entity(client, identifier)).weight
