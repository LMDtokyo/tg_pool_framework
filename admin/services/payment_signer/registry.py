from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Callable

from payment_signer.chain import BroadcastResult


class SweepRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegisteredSweep:
    sweep_id: str
    source_address: str
    amount: Decimal
    transaction_hash: str
    balance_before: Decimal
    destination_address: str = ""

    def as_broadcast_result(self) -> BroadcastResult:
        return BroadcastResult(
            transaction_hash=self.transaction_hash,
            amount=self.amount,
            balance_before=self.balance_before,
            destination_address=self.destination_address,
        )


class SweepRegistry:
    """Local signer-side idempotency store.

    The payment database remains the audit authority. This small registry
    prevents a repeated internal request from broadcasting a second transfer.
    Run one signer process per registry file.
    """

    def __init__(self, database_path: str) -> None:
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(path.resolve())
        self._lock = Lock()
        with self._connect() as connection:
            self._ensure_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=30)

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS signer_sweeps (
                sweep_id TEXT PRIMARY KEY,
                source_address TEXT NOT NULL,
                amount TEXT NOT NULL,
                transaction_hash TEXT NOT NULL,
                balance_before TEXT NOT NULL,
                destination_address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS signer_settings (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        sweep_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(signer_sweeps)")
        }
        if "destination_address" not in sweep_columns:
            connection.execute(
                "ALTER TABLE signer_sweeps "
                "ADD COLUMN destination_address TEXT NOT NULL DEFAULT ''"
            )

    def execute_once(
        self,
        *,
        sweep_id: str,
        source_address: str,
        amount: Decimal,
        operation: Callable[[], BroadcastResult],
    ) -> BroadcastResult:
        with self._lock:
            with self._connect() as connection:
                self._ensure_schema(connection)
                row = connection.execute(
                    """
                    SELECT source_address, amount, transaction_hash, balance_before,
                           destination_address
                    FROM signer_sweeps
                    WHERE sweep_id = ?
                    """,
                    (sweep_id,),
                ).fetchone()
                if row is not None:
                    registered = RegisteredSweep(
                        sweep_id=sweep_id,
                        source_address=str(row[0]),
                        amount=Decimal(str(row[1])),
                        transaction_hash=str(row[2]),
                        balance_before=Decimal(str(row[3])),
                        destination_address=str(row[4]),
                    )
                    if (
                        registered.source_address != source_address
                        or registered.amount != amount
                    ):
                        raise SweepRegistryError(
                            "Sweep ID was already used for another transfer"
                        )
                    return registered.as_broadcast_result()

                result = operation()
                connection.execute(
                    """
                    INSERT INTO signer_sweeps (
                        sweep_id,
                        source_address,
                        amount,
                        transaction_hash,
                        balance_before,
                        destination_address
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sweep_id,
                        source_address,
                        format(result.amount, "f"),
                        result.transaction_hash,
                        format(result.balance_before, "f"),
                        result.destination_address,
                    ),
                )
                connection.commit()
                return result

    def setting(self, name: str) -> str | None:
        with self._lock:
            with self._connect() as connection:
                self._ensure_schema(connection)
                row = connection.execute(
                    "SELECT value FROM signer_settings WHERE name = ?", (name,)
                ).fetchone()
                return str(row[0]) if row is not None else None

    def set_setting(self, name: str, value: str) -> None:
        with self._lock:
            with self._connect() as connection:
                self._ensure_schema(connection)
                connection.execute(
                    """
                    INSERT INTO signer_settings (name, value)
                    VALUES (?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        value = excluded.value,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (name, value),
                )
                connection.commit()
