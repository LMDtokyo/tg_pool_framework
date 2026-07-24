"""tests/test_forward_source.py — src/messaging/forward_source.py."""

from __future__ import annotations

import random

import pytest

from src.messaging.forward_source import parse_message_link, resolve_forward_source

pytestmark = pytest.mark.unit


class TestParseMessageLink:
    def test_public_link_with_scheme(self):
        assert parse_message_link("https://t.me/pythondev/12345") == ("pythondev", 12345)

    def test_public_link_without_scheme(self):
        assert parse_message_link("t.me/pythondev/12345") == ("pythondev", 12345)

    def test_private_channel_link(self):
        assert parse_message_link("https://t.me/c/1234567890/42") == (-1001234567890, 42)

    def test_private_channel_link_without_scheme(self):
        assert parse_message_link("t.me/c/1234567890/42") == (-1001234567890, 42)

    def test_not_a_message_link_returns_none(self):
        assert parse_message_link("https://t.me/pythondev") is None

    def test_garbage_returns_none(self):
        assert parse_message_link("not a link at all") is None

    def test_empty_string_returns_none(self):
        assert parse_message_link("") is None

    def test_whitespace_trimmed(self):
        assert parse_message_link("  t.me/pythondev/5  ") == ("pythondev", 5)


class TestResolveForwardSource:
    def test_forward_link_takes_precedence(self):
        result = resolve_forward_source(
            forward_link="t.me/pythondev/5",
            bot_relay_username="postbot",
            bot_relay_message_ids=[1, 2, 3],
        )
        assert result == ("pythondev", 5)

    def test_bot_relay_used_when_no_forward_link(self):
        result = resolve_forward_source(
            forward_link=None,
            bot_relay_username="@postbot",
            bot_relay_message_ids=[10, 20, 30],
        )
        assert result[0] == "postbot"  # leading @ stripped
        assert result[1] in (10, 20, 30)

    def test_bot_relay_random_choice_deterministic_with_seed(self):
        rng = random.Random(7)
        result = resolve_forward_source(
            forward_link=None,
            bot_relay_username="postbot",
            bot_relay_message_ids=[10, 20, 30],
            rng=rng,
        )
        assert result[1] in (10, 20, 30)

    def test_nothing_configured_returns_none(self):
        assert resolve_forward_source(None, None, None) is None

    def test_bot_relay_without_ids_returns_none(self):
        assert resolve_forward_source(None, "postbot", None) is None

    def test_bot_relay_without_username_returns_none(self):
        assert resolve_forward_source(None, None, [1, 2, 3]) is None

    def test_unparseable_forward_link_falls_back_to_bot_relay(self):
        result = resolve_forward_source(
            forward_link="not a link",
            bot_relay_username="postbot",
            bot_relay_message_ids=[99],
        )
        assert result == ("postbot", 99)
