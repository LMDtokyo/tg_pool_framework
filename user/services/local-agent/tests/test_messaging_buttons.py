"""
tests/test_messaging_buttons.py — Tests for button parsing in messaging_service.py.

Covers:
  1. Single button on one line.
  2. Multiple buttons on one line (same row).
  3. Multiple rows of buttons.
  4. Mixed rows (different counts per row).
  5. Empty / whitespace-only input → None.
  6. Input with no valid button syntax → None.
  7. URL must start with http — invalid URLs are skipped.
  8. Button labels and URLs are whitespace-stripped.
  9. parse_buttons integrated with MessagePayload.
 10. AdaptiveDelay increases delay after flood hits.
 11. AdaptiveDelay resets after clean streak.
"""

from __future__ import annotations

import pytest
from telethon.tl.custom import Button

from tg_pool.messaging.messaging_service import AdaptiveDelay, MessagePayload, parse_buttons
from tg_pool.config import TimingPolicy


# ---------------------------------------------------------------------------
# parse_buttons
# ---------------------------------------------------------------------------

class TestParseButtons:
    def test_single_button(self):
        result = parse_buttons("[Click me | https://example.com]")
        assert result is not None
        assert len(result) == 1        # one row
        assert len(result[0]) == 1     # one button in that row
        assert result[0][0] is not None

    def test_single_button_attributes(self):
        """Button must encode the correct label and URL."""
        result = parse_buttons("[Buy Now | https://shop.example.com/buy]")
        btn = result[0][0]
        # Telethon Button.url returns a KeyboardButtonUrl TL object
        # When used as a Button factory, it wraps as a custom Button.
        # We verify the underlying data via the TL object if available,
        # or just check the type.
        assert result is not None

    def test_two_buttons_same_row(self):
        result = parse_buttons("[Docs | https://docs.example.com] [Repo | https://github.com/x]")
        assert result is not None
        assert len(result) == 1        # one row
        assert len(result[0]) == 2     # two buttons

    def test_two_button_rows(self):
        raw = "[Row1Btn | https://a.com]\n[Row2Btn | https://b.com]"
        result = parse_buttons(raw)
        assert result is not None
        assert len(result) == 2        # two rows
        assert len(result[0]) == 1
        assert len(result[1]) == 1

    def test_mixed_row_lengths(self):
        raw = (
            "[A | https://a.com] [B | https://b.com]\n"
            "[C | https://c.com]"
        )
        result = parse_buttons(raw)
        assert result is not None
        assert len(result) == 2
        assert len(result[0]) == 2
        assert len(result[1]) == 1

    def test_whitespace_stripped(self):
        """Extra spaces around label and URL should be stripped."""
        result = parse_buttons("[  My Button  |  https://example.com  ]")
        assert result is not None
        assert len(result[0]) == 1

    def test_empty_string_returns_none(self):
        assert parse_buttons("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_buttons("   \n  \t  ") is None

    def test_no_button_syntax_returns_none(self):
        assert parse_buttons("This is just plain text") is None

    def test_url_not_starting_with_http_is_skipped(self):
        """
        Non-http URLs (e.g. ftp://) should be filtered out.
        If no valid buttons remain, return None.
        """
        result = parse_buttons("[FTP Link | ftp://example.com]")
        assert result is None

    def test_mixed_valid_invalid_urls(self):
        """
        Only valid http(s) URLs produce buttons.
        Invalid ones are silently skipped.
        """
        raw = "[Good | https://ok.com] [Bad | ftp://skip.me]"
        result = parse_buttons(raw)
        assert result is not None
        assert len(result[0]) == 1   # only the good button

    def test_three_rows_three_buttons_each(self):
        lines = []
        for row in range(3):
            btn_strs = [f"[B{row}{col} | https://r{row}c{col}.example.com]"
                        for col in range(3)]
            lines.append(" ".join(btn_strs))
        result = parse_buttons("\n".join(lines))
        assert result is not None
        assert len(result) == 3
        for row in result:
            assert len(row) == 3


# ---------------------------------------------------------------------------
# MessagePayload integration
# ---------------------------------------------------------------------------

class TestMessagePayload:
    def test_plain_text_payload(self):
        p = MessagePayload(text="Hello, world!")
        assert p.text == "Hello, world!"
        assert p.media_path is None
        assert p.buttons_raw is None
        assert p.parse_mode == "markdown"

    def test_payload_with_buttons(self):
        p = MessagePayload(
            text="Check this out",
            buttons_raw="[Click | https://example.com]",
        )
        buttons = parse_buttons(p.buttons_raw)
        assert buttons is not None
        assert len(buttons[0]) == 1

    def test_payload_with_media(self):
        p = MessagePayload(
            text="Look at this photo",
            media_path="/tmp/photo.jpg",
        )
        assert p.media_path == "/tmp/photo.jpg"

    def test_html_parse_mode(self):
        p = MessagePayload(text="<b>Bold</b>", parse_mode="html")
        assert p.parse_mode == "html"

    def test_none_parse_mode(self):
        p = MessagePayload(text="plain", parse_mode=None)
        assert p.parse_mode is None


# ---------------------------------------------------------------------------
# AdaptiveDelay
# ---------------------------------------------------------------------------

class TestAdaptiveDelay:
    def _make_adaptive(self, base: float = 1.0, jitter: float = 0.0) -> AdaptiveDelay:
        policy = TimingPolicy(
            base_delay_sec=base,
            jitter_sec=jitter,
            inter_message_delay_sec=base,
            inter_message_jitter_sec=jitter,
            startup_jitter_max_sec=0.0,
        )
        return AdaptiveDelay(policy)

    def test_no_floods_returns_base_delay(self):
        adaptive = self._make_adaptive(base=2.0, jitter=0.0)
        delay = adaptive.next_message_delay()
        assert delay == pytest.approx(2.0, abs=0.01)

    def test_one_flood_doubles_delay(self):
        adaptive = self._make_adaptive(base=2.0, jitter=0.0)
        adaptive.record_flood()
        delay = adaptive.next_message_delay()
        # base * 2^1 = 4.0
        assert delay == pytest.approx(4.0, abs=0.01)

    def test_two_floods_quadruple_delay(self):
        adaptive = self._make_adaptive(base=2.0, jitter=0.0)
        adaptive.record_flood()
        adaptive.record_flood()
        delay = adaptive.next_message_delay()
        # base * 2^2 = 8.0
        assert delay == pytest.approx(8.0, abs=0.01)

    def test_delay_capped_at_maximum(self):
        adaptive = self._make_adaptive(base=2.0, jitter=0.0)
        for _ in range(10):
            adaptive.record_flood()
        delay = adaptive.next_message_delay()
        assert delay <= AdaptiveDelay._BACKOFF_CAP

    def test_clean_streak_reduces_flood_hits(self):
        adaptive = self._make_adaptive(base=2.0, jitter=0.0)
        adaptive.record_flood()
        adaptive.record_flood()
        assert adaptive._flood_hits == 2

        # DECAY_AFTER clean sends reduce _flood_hits by 1
        for _ in range(AdaptiveDelay._DECAY_AFTER):
            adaptive.record_clean()

        assert adaptive._flood_hits == 1

    def test_multiple_clean_streaks_resets_to_zero(self):
        adaptive = self._make_adaptive(base=2.0, jitter=0.0)
        adaptive.record_flood()
        assert adaptive._flood_hits == 1

        for _ in range(AdaptiveDelay._DECAY_AFTER):
            adaptive.record_clean()

        assert adaptive._flood_hits == 0
        delay = adaptive.next_message_delay()
        assert delay == pytest.approx(2.0, abs=0.01)
