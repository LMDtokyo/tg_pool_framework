"""
tests/test_entity_resolver.py — Tests for tg_pool/entity_resolver.py.

All Telethon network calls are mocked.

Test scenarios:
  1.  @username          → supergroup (Channel, megagroup=True)
  2.  plain username     → same
  3.  t.me/username      → broadcast channel (Channel, megagroup=False)
  4.  Raw integer ID     → regular chat (Chat)
  5.  t.me/+HASH         → already member (ChatInviteAlready) → no join
  6.  t.me/joinchat/HASH → not a member → ImportChatInviteRequest called
  7.  Concurrent join (UserAlreadyParticipantError) → re-checks and succeeds
  8.  Expired hash       → ValueError raised
  9.  Invalid hash       → ValueError raised
  10. EntityKind classification: CHANNEL / SUPERGROUP / CHAT / UNKNOWN
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from telethon.errors import (
    InviteHashExpiredError,
    InviteHashInvalidError,
    UserAlreadyParticipantError,
)
from telethon.tl.types import Channel, Chat, ChatInviteAlready, ChatInvitePeek

from tg_pool.extraction.entity_resolver import (
    EntityInfo,
    EntityKind,
    ResolvedEntity,
    UniversalEntityResolver,
    _classify,
    describe_entity,
    estimate_entity_weight,
)


# ---------------------------------------------------------------------------
# Helpers: build mock Telethon entities that pass isinstance() checks
# ---------------------------------------------------------------------------

def make_channel(*, megagroup: bool, title: str = "Test Channel", forum: bool = False) -> MagicMock:
    """Creates a MagicMock that isinstance(obj, Channel) returns True."""
    obj = MagicMock()
    obj.__class__ = Channel
    obj.megagroup = megagroup
    obj.broadcast = not megagroup
    obj.title = title
    obj.id = 100
    obj.forum = forum
    return obj


def make_chat(title: str = "Test Chat") -> MagicMock:
    """Creates a MagicMock that isinstance(obj, Chat) returns True."""
    obj = MagicMock()
    obj.__class__ = Chat
    obj.title = title
    obj.id = 200
    obj.forum = False  # real Chat has no forum field; matches getattr(..., "forum", False)
    return obj


def make_client(
    entity: MagicMock,
    call_return=None,
) -> AsyncMock:
    """
    Builds a mock TelegramClient.

    client(Request)        → call_return  (for CheckChatInvite / Import)
    client.get_entity(...) → entity
    client.get_input_entity(...) → MagicMock InputPeer
    """
    client = AsyncMock()
    client.return_value = call_return  # await client(SomeRequest)
    client.get_entity = AsyncMock(return_value=entity)
    client.get_input_entity = AsyncMock(return_value=MagicMock(name="InputPeer"))
    return client


# ---------------------------------------------------------------------------
# _classify() — pure function, no async needed
# ---------------------------------------------------------------------------

class TestClassify:
    def test_supergroup(self):
        assert _classify(make_channel(megagroup=True)) == EntityKind.SUPERGROUP

    def test_broadcast_channel(self):
        assert _classify(make_channel(megagroup=False)) == EntityKind.CHANNEL

    def test_regular_chat(self):
        assert _classify(make_chat()) == EntityKind.CHAT

    def test_unknown(self):
        assert _classify(MagicMock()) == EntityKind.UNKNOWN


# ---------------------------------------------------------------------------
# Public identifier resolution
# ---------------------------------------------------------------------------

class TestResolvePublic:
    async def test_at_username_resolves_to_supergroup(self):
        entity = make_channel(megagroup=True, title="PyCommunity")
        client = make_client(entity)

        result = await UniversalEntityResolver(client).resolve("@pycommunity")

        client.get_entity.assert_called_once_with("pycommunity")
        assert result.kind == EntityKind.SUPERGROUP
        assert result.title == "PyCommunity"

    async def test_plain_username_without_at(self):
        entity = make_channel(megagroup=True)
        client = make_client(entity)

        await UniversalEntityResolver(client).resolve("pycommunity")

        client.get_entity.assert_called_once_with("pycommunity")

    async def test_public_tme_link_resolves_username(self):
        entity = make_channel(megagroup=False, title="News")
        client = make_client(entity)

        result = await UniversalEntityResolver(client).resolve("https://t.me/news_channel")

        client.get_entity.assert_called_once_with("news_channel")
        assert result.kind == EntityKind.CHANNEL

    async def test_raw_integer_id(self):
        entity = make_chat(title="Private Group")
        client = make_client(entity)

        result = await UniversalEntityResolver(client).resolve("-1001234567890")

        client.get_entity.assert_called_once_with(-1001234567890)
        assert result.kind == EntityKind.CHAT

    async def test_get_input_entity_called_with_resolved_entity(self):
        entity = make_channel(megagroup=True)
        client = make_client(entity)

        await UniversalEntityResolver(client).resolve("@somegroup")

        client.get_input_entity.assert_called_once_with(entity)


# ---------------------------------------------------------------------------
# Private invite links — already a member
# ---------------------------------------------------------------------------

class TestResolveInviteAlreadyMember:
    async def test_joinchat_link_already_member(self):
        chat = make_channel(megagroup=True, title="Secret Group")
        invite_already = MagicMock(spec=ChatInviteAlready)
        invite_already.chat = chat

        client = make_client(entity=chat, call_return=invite_already)

        result = await UniversalEntityResolver(client).resolve("t.me/joinchat/ABCDEF123456")

        # Import must NOT be called
        from telethon.tl.functions.messages import ImportChatInviteRequest
        for c in client.call_args_list:
            assert not isinstance(c.args[0] if c.args else None,
                                  ImportChatInviteRequest), \
                "ImportChatInviteRequest should not be called when already a member"

        assert result.kind == EntityKind.SUPERGROUP
        assert result.title == "Secret Group"

    async def test_plus_hash_link_already_member_via_peek(self):
        chat = make_chat(title="Peek Group")
        invite_peek = MagicMock(spec=ChatInvitePeek)
        invite_peek.chat = chat

        client = make_client(entity=chat, call_return=invite_peek)

        result = await UniversalEntityResolver(client).resolve("https://t.me/+XYZ789")

        assert result.kind == EntityKind.CHAT


# ---------------------------------------------------------------------------
# Private invite links — not a member → auto-join
# ---------------------------------------------------------------------------

class TestResolveInviteJoin:
    async def _make_client_for_join(self, chat):
        """
        First CheckChatInviteRequest → ChatInvite (not a member).
        ImportChatInviteRequest  → Updates object with .chats = [chat].
        """
        from telethon.tl.types import ChatInvite

        invite_new = MagicMock()  # generic ChatInvite (not Already/Peek)
        invite_new.__class__ = ChatInvite
        invite_new.title = chat.title

        import_result = MagicMock()
        import_result.chats = [chat]

        # client() is called twice: Check → Import
        client = AsyncMock()
        client.side_effect = [invite_new, import_result]
        client.get_entity = AsyncMock(return_value=chat)
        client.get_input_entity = AsyncMock(return_value=MagicMock())
        return client

    async def test_not_member_triggers_import(self):
        chat = make_channel(megagroup=True, title="Hidden Group")
        client = await self._make_client_for_join(chat)

        result = await UniversalEntityResolver(client).resolve("t.me/+SECRETHASH")

        assert client.call_count == 2, "Expected CheckChatInvite + ImportChatInvite"
        assert result.kind == EntityKind.SUPERGROUP

    async def test_concurrent_join_race_handled(self):
        """
        UserAlreadyParticipantError during Import → resolver re-checks
        and succeeds without propagating the exception.
        """
        chat = make_channel(megagroup=False, title="Race Channel")

        from telethon.tl.types import ChatInvite

        invite_new = MagicMock()
        invite_new.__class__ = ChatInvite
        invite_new.title = "Race Channel"

        invite_already = MagicMock(spec=ChatInviteAlready)
        invite_already.chat = chat

        client = AsyncMock()
        # 1st call: Check → not member
        # 2nd call: Import → race condition
        # 3rd call: Check again → already member
        client.side_effect = [
            invite_new,
            UserAlreadyParticipantError(request=None),
            invite_already,
        ]
        client.get_entity = AsyncMock(return_value=chat)
        client.get_input_entity = AsyncMock(return_value=MagicMock())

        result = await UniversalEntityResolver(client).resolve("t.me/+RACEHASH")

        assert client.call_count == 3
        assert result.kind == EntityKind.CHANNEL


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestResolveErrors:
    async def test_expired_hash_raises_value_error(self):
        client = AsyncMock()
        client.side_effect = InviteHashExpiredError(request=None)

        with pytest.raises(ValueError, match="expired"):
            await UniversalEntityResolver(client).resolve("t.me/+EXPIREDHASH")

    async def test_invalid_hash_raises_value_error(self):
        client = AsyncMock()
        client.side_effect = InviteHashInvalidError(request=None)

        # Hash must look valid (alphanumeric) so the regex captures it,
        # then the mock raises InviteHashInvalidError from CheckChatInviteRequest.
        with pytest.raises(ValueError, match="invalid"):
            await UniversalEntityResolver(client).resolve("t.me/joinchat/INVALIDBUTPARSEABLE")


# ---------------------------------------------------------------------------
# estimate_entity_weight() — never raises, falls back to 1.0 on any failure
# ---------------------------------------------------------------------------

class TestEstimateEntityWeight:
    async def test_supergroup_uses_get_full_channel_request(self):
        entity = make_channel(megagroup=True, title="Big Group")
        full = MagicMock()
        full.full_chat.participants_count = 50_000
        client = make_client(entity, call_return=full)

        weight = await estimate_entity_weight(client, "@biggroup")

        assert weight == 50_000.0

    async def test_broadcast_channel_uses_get_full_channel_request(self):
        entity = make_channel(megagroup=False, title="Broadcast")
        full = MagicMock()
        full.full_chat.participants_count = 200_000
        client = make_client(entity, call_return=full)

        weight = await estimate_entity_weight(client, "@broadcast")

        assert weight == 200_000.0

    async def test_chat_reads_participants_count_directly_no_extra_rpc(self):
        entity = make_chat(title="Small Chat")
        entity.participants_count = 42
        client = make_client(entity)

        weight = await estimate_entity_weight(client, "-1009876543210")

        assert weight == 42.0
        client.assert_not_called()

    async def test_unknown_kind_falls_back_to_one(self):
        entity = MagicMock()  # not Channel, not Chat -> EntityKind.UNKNOWN
        client = make_client(entity)

        weight = await estimate_entity_weight(client, "@mystery")

        assert weight == 1.0

    async def test_no_rights_falls_back_to_one(self):
        entity = make_channel(megagroup=True, title="Locked")
        client = make_client(entity)
        client.side_effect = Exception("CHAT_ADMIN_REQUIRED")

        weight = await estimate_entity_weight(client, "@locked")

        assert weight == 1.0

    async def test_resolution_failure_falls_back_to_one(self):
        client = AsyncMock()
        client.get_entity = AsyncMock(side_effect=ValueError("no such entity"))

        weight = await estimate_entity_weight(client, "@doesnotexist")

        assert weight == 1.0

    async def test_zero_participants_falls_back_to_one(self):
        entity = make_chat(title="Empty Chat")
        entity.participants_count = 0
        client = make_client(entity)

        weight = await estimate_entity_weight(client, "-1001111111111")

        assert weight == 1.0


# ---------------------------------------------------------------------------
# describe_entity() — combined weight/kind/is_forum, feeds both LPT
# distribution and Lua-based per-entity strategy selection
# ---------------------------------------------------------------------------

class TestDescribeEntity:
    async def test_reports_weight_kind_and_is_forum(self):
        entity = make_channel(megagroup=True, title="Forum Group", forum=True)
        full = MagicMock()
        full.full_chat.participants_count = 5000
        full.full_chat.linked_chat_id = None
        client = make_client(entity, call_return=full)

        info = await describe_entity(client, "@forumgroup")

        assert info == EntityInfo(
            weight=5000.0, kind=EntityKind.SUPERGROUP, is_forum=True, has_discussion=False,
        )

    async def test_channel_with_linked_discussion_group(self):
        entity = make_channel(megagroup=False, title="Broadcast")
        full = MagicMock()
        full.full_chat.participants_count = 10_000
        full.full_chat.linked_chat_id = 555
        client = make_client(entity, call_return=full)

        info = await describe_entity(client, "@broadcast")

        assert info.has_discussion is True

    async def test_channel_without_linked_discussion_group(self):
        entity = make_channel(megagroup=False, title="Broadcast")
        full = MagicMock()
        full.full_chat.participants_count = 10_000
        full.full_chat.linked_chat_id = None
        client = make_client(entity, call_return=full)

        info = await describe_entity(client, "@broadcast")

        assert info.has_discussion is False

    async def test_non_forum_supergroup(self):
        entity = make_channel(megagroup=True, title="Plain Group", forum=False)
        full = MagicMock()
        full.full_chat.participants_count = 300
        client = make_client(entity, call_return=full)

        info = await describe_entity(client, "@plaingroup")

        assert info.is_forum is False
        assert info.kind == EntityKind.SUPERGROUP

    async def test_chat_is_never_a_forum(self):
        entity = make_chat(title="Small Chat")
        entity.participants_count = 10
        client = make_client(entity)

        info = await describe_entity(client, "-1001234567890")

        assert info.kind == EntityKind.CHAT
        assert info.is_forum is False

    async def test_resolution_failure_falls_back_to_defaults(self):
        client = AsyncMock()
        client.get_entity = AsyncMock(side_effect=ValueError("no such entity"))

        info = await describe_entity(client, "@doesnotexist")

        assert info == EntityInfo()
        assert info.weight == 1.0
        assert info.kind == EntityKind.UNKNOWN
        assert info.is_forum is False
