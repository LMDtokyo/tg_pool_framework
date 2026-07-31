"""
license_server/profile_names.py — First/last name pool for auto-filling a
Telegram account's display name at registration (see
src/api/telegram_auth.py's begin()).

Served from here rather than shipped as a constant in every install: a name
pool baked into the client binary is identical across every customer, so
Telegram could in principle correlate "this exact small set of names keeps
showing up across accounts with no other connection to each other" the same
way a shared device-fingerprint catalog would. Centralizing it means the
pool can grow or rotate over time without a new client release, and it's
one shared, larger pool instead of thousands of installs each drawing from
their own frozen copy.
"""

from __future__ import annotations

FIRST_NAMES: tuple[str, ...] = (
    "Alex", "Daniel", "David", "Emma", "James", "Julia", "Leo", "Maria",
    "Mia", "Nora", "Oliver", "Sofia", "Anna", "Ben", "Chloe", "Ethan",
    "Grace", "Henry", "Ivy", "Jack", "Kate", "Liam", "Lucy", "Max",
    "Nina", "Owen", "Paula", "Quinn", "Ryan", "Sara", "Tom", "Vera",
    "Will", "Zoe", "Adam", "Bella", "Carl", "Diana", "Elena", "Felix",
)

LAST_NAMES: tuple[str, ...] = (
    "Adams", "Brown", "Clark", "Davis", "Evans", "Hall", "Lewis", "Martin",
    "Miller", "Moore", "Taylor", "Wilson", "Allen", "Baker", "Carter",
    "Cook", "Cooper", "Diaz", "Edwards", "Fisher", "Foster", "Gray",
    "Green", "Hayes", "Hughes", "James", "Jenkins", "Kelly", "King",
    "Lee", "Long", "Morris", "Murphy", "Parker", "Reed", "Rogers",
    "Ross", "Scott", "Stewart", "Ward",
)
