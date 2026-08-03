import asyncio
import csv
import json

import pytest

from tg_pool.api.json_generator import (
    JsonGeneratorAlreadyRunningError,
    JsonGeneratorManager,
)


pytestmark = pytest.mark.unit


def _write_fingerprint_database(path):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "APP_ID",
                "APP_HASH",
                "SDK",
                "DEVICE",
                "APP_VERSION",
                "LANG_CODE",
                "SYSTEM_LANG_CODE",
                "LANG_PACK",
                "TZ_OFFSET",
                "PERF_CAT",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "APP_ID": 12345,
                "APP_HASH": "0123456789abcdef0123456789abcdef",
                "SDK": 35,
                "DEVICE": "Pixel 9",
                "APP_VERSION": "11.5.3",
                "LANG_CODE": "en",
                "SYSTEM_LANG_CODE": "en-US",
                "LANG_PACK": "android",
                "TZ_OFFSET": 0,
                "PERF_CAT": 2,
            }
        )


async def _wait_until_finished(manager):
    for _ in range(100):
        if not manager.is_running:
            return
        await asyncio.sleep(0.01)
    pytest.fail("JSON generator did not finish")


async def test_generates_telegram_expert_pair_without_modifying_source(tmp_path):
    database = tmp_path / "fingerprints.csv"
    sessions = tmp_path / "sessions"
    output = tmp_path / "output"
    sessions.mkdir()
    source = sessions / "15551234567.session"
    source.write_bytes(b"session-data")
    _write_fingerprint_database(database)

    manager = JsonGeneratorManager()
    manager.start(str(database), str(sessions), str(output))
    await _wait_until_finished(manager)

    status = manager.status()
    assert status["finished"] is True
    assert status["total"] == 1
    assert status["results"][0]["success"] is True
    assert source.read_bytes() == b"session-data"
    assert (output / source.name).read_bytes() == b"session-data"

    payload = json.loads((output / "15551234567.json").read_text(encoding="utf-8"))
    assert payload["phone"] == "+15551234567"
    assert payload["app_id"] == 12345
    assert payload["app_hash"] == "0123456789abcdef0123456789abcdef"
    assert payload["device"] == "Pixel 9"


def _write_multi_row_fingerprint_database(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "APP_ID", "APP_HASH", "SDK", "DEVICE", "APP_VERSION",
                "LANG_CODE", "SYSTEM_LANG_CODE", "LANG_PACK", "TZ_OFFSET", "PERF_CAT",
            ],
        )
        writer.writeheader()
        for device, app_version in rows:
            writer.writerow({
                "APP_ID": 12345, "APP_HASH": "0123456789abcdef0123456789abcdef", "SDK": 35,
                "DEVICE": device, "APP_VERSION": app_version, "LANG_CODE": "en",
                "SYSTEM_LANG_CODE": "en-US", "LANG_PACK": "android", "TZ_OFFSET": 0, "PERF_CAT": 2,
            })


async def test_batch_generation_assigns_distinct_fingerprints_when_catalog_allows(tmp_path):
    database = tmp_path / "fingerprints.csv"
    sessions = tmp_path / "sessions"
    output = tmp_path / "output"
    sessions.mkdir()
    for phone in ["15551111111", "15552222222", "15553333333"]:
        (sessions / f"{phone}.session").write_bytes(b"session-data")
    _write_multi_row_fingerprint_database(
        database, [("Pixel 9", "11.5.3"), ("Galaxy S24", "10.2.0"), ("iPhone 15", "10.9.0")]
    )

    manager = JsonGeneratorManager()
    manager.start(str(database), str(sessions), str(output))
    await _wait_until_finished(manager)

    assert manager.status()["finished"] is True
    signatures = set()
    for phone in ["15551111111", "15552222222", "15553333333"]:
        payload = json.loads((output / f"{phone}.json").read_text(encoding="utf-8"))
        signatures.add((payload["device"], payload["app_version"]))
    assert len(signatures) == 3  # no duplicates handed out across the batch


async def test_rejects_a_second_run_while_generation_is_active(tmp_path, monkeypatch):
    database = tmp_path / "fingerprints.csv"
    sessions = tmp_path / "sessions"
    output = tmp_path / "output"
    sessions.mkdir()
    (sessions / "1.session").write_bytes(b"one")
    _write_fingerprint_database(database)

    manager = JsonGeneratorManager()
    original_sleep = asyncio.sleep

    async def slow_sleep(_delay):
        await original_sleep(0.05)

    monkeypatch.setattr("tg_pool.api.json_generator.asyncio.sleep", slow_sleep)
    manager.start(str(database), str(sessions), str(output))

    with pytest.raises(JsonGeneratorAlreadyRunningError):
        manager.start(str(database), str(sessions), str(output))

    await manager.stop()
    assert manager.status()["cancelled"] is True
