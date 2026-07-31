"""tests/test_security_utils.py — src/api/security_utils.scrub_secrets."""

from __future__ import annotations

import pytest

from src.api.security_utils import scrub_secrets

pytestmark = pytest.mark.unit


def test_redacts_a_32_char_hex_api_hash():
    text = "RPCError: bad request, api_hash=0123456789abcdef0123456789abcdef rejected"
    assert "0123456789abcdef0123456789abcdef" not in scrub_secrets(text)
    assert "[redacted]" in scrub_secrets(text)


def test_redacts_credentials_embedded_in_a_url():
    text = "ProxyConnectionError: socks5://user:hunter2@10.0.0.1:1080 unreachable"
    scrubbed = scrub_secrets(text)
    assert "user:hunter2" not in scrubbed
    assert "socks5://[redacted]@10.0.0.1:1080" in scrubbed


def test_leaves_unrelated_text_unchanged():
    text = "PeerFloodError: too many requests, try again later"
    assert scrub_secrets(text) == text


def test_does_not_touch_short_hex_looking_substrings():
    text = "error code 0xdeadbeef occurred"
    assert scrub_secrets(text) == text
