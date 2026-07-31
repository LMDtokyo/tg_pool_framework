"""tests/test_events.py — src/api/events.py's WS event forwarding allowlist."""

from __future__ import annotations

import pytest

from src.api.events import _FORWARDED_EVENTS, _serialize
from src.monitoring.event_bus import AccountsDiscoveredEvent

pytestmark = pytest.mark.unit


def test_accounts_discovered_event_is_forwarded_to_the_ui():
    assert AccountsDiscoveredEvent in _FORWARDED_EVENTS


def test_accounts_discovered_event_serializes_with_its_class_name_as_type():
    event = AccountsDiscoveredEvent(
        loaded_count=2, loaded_phones=["+7001", "+7002"], failed_count=1, failed_reasons=["x.session: bad"]
    )
    envelope = _serialize(event)

    assert envelope["type"] == "AccountsDiscoveredEvent"
    assert envelope["data"]["loaded_count"] == 2
    assert envelope["data"]["loaded_phones"] == ["+7001", "+7002"]
    assert envelope["data"]["failed_reasons"] == ["x.session: bad"]
