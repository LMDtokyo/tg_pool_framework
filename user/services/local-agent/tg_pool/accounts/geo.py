"""
tg_pool/accounts/geo.py — Account geo (country) derived from phone number.

Uses `phonenumbers` (Google libphonenumber port) rather than a hand-rolled
calling-code table — accurate across shared calling codes (e.g. +1 spans
US/Canada/Caribbean) and edge cases a manual prefix map would get wrong.
Pure/offline: no network call, so it can never fail on connectivity — only
on a malformed number, which yields None rather than raising.
"""

from __future__ import annotations

from typing import Optional

import phonenumbers


def country_for_phone(phone: str) -> Optional[str]:
    """
    Return the 2-letter ISO region code (e.g. "RU", "US") for a phone number,
    or None if the number can't be parsed or maps to no region.
    """
    try:
        parsed = phonenumbers.parse(phone, None)
    except phonenumbers.NumberParseException:
        return None
    return phonenumbers.region_code_for_number(parsed)
