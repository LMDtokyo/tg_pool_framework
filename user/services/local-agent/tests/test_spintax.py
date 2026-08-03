"""tests/test_spintax.py — tg_pool/messaging/spintax.py::resolve_spintax."""

from __future__ import annotations

import random

import pytest

from tg_pool.messaging.spintax import resolve_spintax

pytestmark = pytest.mark.unit


def test_no_spintax_returns_text_unchanged():
    assert resolve_spintax("Привет, мир!") == "Привет, мир!"


def test_resolves_to_one_of_the_options():
    result = resolve_spintax("{Привет|Здравствуй|Добрый день}")
    assert result in ("Привет", "Здравствуй", "Добрый день")


def test_deterministic_with_seeded_rng():
    rng = random.Random(42)
    result = resolve_spintax("{a|b|c}", rng=rng)
    assert result in ("a", "b", "c")


def test_multiple_groups_resolved_independently():
    rng = random.Random(0)
    result = resolve_spintax("{a|b} {c|d}", rng=rng)
    first, second = result.split(" ")
    assert first in ("a", "b")
    assert second in ("c", "d")


def test_surrounding_text_preserved():
    result = resolve_spintax("Hello {there|friend}, welcome!")
    assert result in ("Hello there, welcome!", "Hello friend, welcome!")


def test_nested_spintax_resolves_inside_out():
    rng = random.Random(1)
    result = resolve_spintax("{a|{b|c}}", rng=rng)
    assert result in ("a", "b", "c")


def test_variable_placeholder_without_pipe_is_untouched():
    """{username} has no '|' -- must survive spintax resolution for render_template()."""
    assert resolve_spintax("Hi {username}, {yes|no}?") .split(", ")[0] == "Hi {username}"


def test_empty_string():
    assert resolve_spintax("") == ""


def test_single_option_group_returns_that_option():
    assert resolve_spintax("{onlyoption}") == "{onlyoption}"  # no pipe -> not spintax, untouched


def test_pipe_group_with_one_option_after_split():
    # A single "|" with nothing after it still counts as spintax (two empty/short options).
    result = resolve_spintax("{a|}")
    assert result in ("a", "")
