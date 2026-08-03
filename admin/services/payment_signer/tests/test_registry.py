from decimal import Decimal

import pytest

from payment_signer.chain import BroadcastResult
from payment_signer.registry import SweepRegistry, SweepRegistryError


def test_registry_executes_each_sweep_id_once(tmp_path):
    registry = SweepRegistry(str(tmp_path / "signer.db"))
    calls = []

    def operation():
        calls.append(True)
        return BroadcastResult("tx-1", Decimal("5"), Decimal("10"), "TTreasury")

    first = registry.execute_once(
        sweep_id="1",
        source_address="TSource",
        amount=Decimal("5"),
        operation=operation,
    )
    replay = registry.execute_once(
        sweep_id="1",
        source_address="TSource",
        amount=Decimal("5"),
        operation=operation,
    )

    assert first == replay
    assert replay.destination_address == "TTreasury"
    assert len(calls) == 1

    with pytest.raises(SweepRegistryError):
        registry.execute_once(
            sweep_id="1",
            source_address="TSource",
            amount=Decimal("6"),
            operation=operation,
        )


def test_registry_persists_signer_settings(tmp_path):
    path = str(tmp_path / "signer.db")
    registry = SweepRegistry(path)

    assert registry.setting("treasury_address") is None
    registry.set_setting("treasury_address", "TNewTreasury")

    assert SweepRegistry(path).setting("treasury_address") == "TNewTreasury"


def test_registry_recreates_schema_if_database_file_is_emptied(tmp_path):
    path = tmp_path / "nested" / "signer.db"
    registry = SweepRegistry(str(path))
    registry.set_setting("treasury_address", "TTreasury")
    path.write_bytes(b"")

    recovered = SweepRegistry(str(path))
    assert recovered.setting("treasury_address") is None
    result = recovered.execute_once(
        sweep_id="recover-1",
        source_address="TSource",
        amount=Decimal("1"),
        operation=lambda: BroadcastResult("tx-recover", Decimal("1"), Decimal("2"), "TTreasury"),
    )
    assert result.transaction_hash == "tx-recover"
