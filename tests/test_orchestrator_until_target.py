"""tests/test_orchestrator_until_target.py — Tests for orchestrate_until_target(), the exact-total-count cycling wrapper around orchestrate_multi_source()."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from src.messaging.messaging_service import BatchReport
from src.orchestrator import orchestrate_until_target


def make_report(succeeded: int, sent_recipients: set, total: int = None, failed: int = 0) -> BatchReport:
    return BatchReport(
        total=total if total is not None else succeeded + failed,
        succeeded=succeeded,
        failed=failed,
        per_account={"+79001234567": succeeded},
        sent_recipients=set(sent_recipients),
    )


async def test_stops_after_single_cycle_when_target_reached():
    with patch(
        "src.orchestrator.orchestrate_multi_source",
        side_effect=[make_report(5, {"a", "b", "c", "d", "e"})],
    ) as mock_send:
        report = await orchestrate_until_target(exact_total_target=5, accounts=[])

    assert mock_send.call_count == 1
    assert report.succeeded == 5
    assert report.sent_recipients == {"a", "b", "c", "d", "e"}


async def test_cycles_accumulate_excludes_and_totals():
    captured_calls = []

    async def fake_orchestrate(**kwargs):
        excluded = kwargs.get("exclude_recipients")
        captured_calls.append(set(excluded) if excluded else None)
        if len(captured_calls) == 1:
            return make_report(3, {"a", "b", "c"})
        return make_report(2, {"d", "e"})

    with patch("src.orchestrator.orchestrate_multi_source", side_effect=fake_orchestrate):
        report = await orchestrate_until_target(exact_total_target=5, accounts=[])

    assert len(captured_calls) == 2
    assert captured_calls[0] is None
    assert captured_calls[1] == {"a", "b", "c"}
    assert report.succeeded == 5
    assert report.total == 5
    assert report.per_account["+79001234567"] == 5
    assert report.sent_recipients == {"a", "b", "c", "d", "e"}


async def test_stops_when_cycle_finds_no_new_recipients():
    with patch(
        "src.orchestrator.orchestrate_multi_source",
        side_effect=[make_report(3, {"a", "b", "c"}), make_report(0, set())],
    ) as mock_send:
        report = await orchestrate_until_target(exact_total_target=100, accounts=[])

    assert mock_send.call_count == 2
    assert report.succeeded == 3


async def test_max_cycles_safety_valve_stops_infinite_loop():
    call_count = 0

    async def fake_orchestrate(**kwargs):
        nonlocal call_count
        call_count += 1
        return make_report(1, {f"user{call_count}"})

    with patch("src.orchestrator.orchestrate_multi_source", side_effect=fake_orchestrate):
        report = await orchestrate_until_target(exact_total_target=1000, max_cycles=3, accounts=[])

    assert call_count == 3
    assert report.succeeded == 3


async def test_shutdown_event_already_set_skips_all_cycles():
    shutdown_event = asyncio.Event()
    shutdown_event.set()

    with patch("src.orchestrator.orchestrate_multi_source") as mock_send:
        report = await orchestrate_until_target(
            exact_total_target=5, accounts=[], shutdown_event=shutdown_event,
        )

    mock_send.assert_not_called()
    assert report.total == 0
