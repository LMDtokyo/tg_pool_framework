"""tests/test_geo.py — Phone-number -> country lookup."""

import pytest

from tg_pool.accounts.geo import country_for_phone

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "phone, expected",
    [
        ("+79001234567", "RU"),
        ("+12025551234", "US"),
        ("+442083661177", "GB"),
        ("+8613800138000", "CN"),
    ],
)
def test_known_country_codes(phone, expected):
    assert country_for_phone(phone) == expected


def test_invalid_number_returns_none():
    assert country_for_phone("not-a-phone-number") is None


def test_empty_string_returns_none():
    assert country_for_phone("") is None


def test_number_without_plus_prefix_returns_none():
    # No default region supplied -> phonenumbers can't disambiguate a bare
    # national-format number; this must fail closed (None), not raise.
    assert country_for_phone("9001234567") is None
