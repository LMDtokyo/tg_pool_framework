from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from threading import RLock

from payment_signer.keyvault import KeyVault, KeyVaultError
from payment_signer.money import token_amount


class ChainError(RuntimeError):
    pass


@dataclass(frozen=True)
class BroadcastResult:
    transaction_hash: str
    amount: Decimal
    balance_before: Decimal
    destination_address: str = ""


@dataclass(frozen=True)
class TransactionStatus:
    status: str
    balance_after: Optional[Decimal]
    network_fee: Optional[Decimal]
    error_message: str = ""


class TronSweepService:
    def __init__(self, vault: KeyVault, treasury_address: str | None = None) -> None:
        self._vault = vault
        self._treasury_lock = RLock()
        self._treasury = (
            treasury_address
            if treasury_address is not None
            else os.getenv("SIGNER_TREASURY_ADDRESS", "")
        ).strip()
        self._contract_address = os.getenv("SIGNER_TRC20_CONTRACT", "").strip()
        self._network = os.getenv("SIGNER_TRON_NETWORK", "mainnet").strip().lower()
        self._fee_limit = int(os.getenv("SIGNER_FEE_LIMIT_SUN", "100000000"))
        if not self._treasury or not self._contract_address:
            raise RuntimeError(
                "SIGNER_TREASURY_ADDRESS and SIGNER_TRC20_CONTRACT must be configured"
            )
        if self._network not in {"mainnet", "nile", "shasta", "tronex"}:
            raise RuntimeError("SIGNER_TRON_NETWORK is invalid")
        if self._fee_limit <= 0:
            raise RuntimeError("SIGNER_FEE_LIMIT_SUN must be greater than zero")
        self._client = self._build_client()
        if not self._client.is_address(self._treasury):
            raise RuntimeError("SIGNER_TREASURY_ADDRESS is invalid")
        if not self._client.is_address(self._contract_address):
            raise RuntimeError("SIGNER_TRC20_CONTRACT is invalid")
        self._contract = self._client.get_contract(self._contract_address)
        self._decimals = int(self._contract.functions.decimals())
        if self._decimals < 0 or self._decimals > 30:
            raise RuntimeError("TRC20 contract returned invalid decimals")
        self._validate_vault()

    @property
    def treasury_address(self) -> str:
        with self._treasury_lock:
            return self._treasury

    def set_treasury_address(self, address: str) -> str:
        address = address.strip()
        if not self._client.is_address(address):
            raise ChainError("Administrator wallet address is invalid")
        with self._treasury_lock:
            self._treasury = address
        return address

    @property
    def contract_address(self) -> str:
        return self._contract_address

    @property
    def network(self) -> str:
        return self._network

    def _build_client(self):
        from tronpy import Tron
        from tronpy.providers import HTTPProvider

        endpoint = os.getenv("SIGNER_TRON_HTTP_ENDPOINT", "").strip() or None
        api_key = os.getenv("TRONGRID_API_KEY", "").strip() or None
        if endpoint:
            return Tron(
                HTTPProvider(endpoint_uri=endpoint, api_key=api_key),
                network=self._network,
            )
        if api_key and self._network == "mainnet":
            return Tron(HTTPProvider(api_key=api_key), network=self._network)
        return Tron(network=self._network)

    def _private_key(self, address: str):
        from tronpy.keys import PrivateKey

        try:
            key = PrivateKey.fromhex(self._vault.private_key_hex(address))
        except (ValueError, KeyVaultError) as exc:
            raise ChainError(str(exc)) from exc
        if key.public_key.to_base58check_address() != address:
            raise ChainError("Vault key does not match the requested source address")
        return key

    def _validate_vault(self) -> None:
        for address in self._vault.addresses():
            if not self._client.is_address(address):
                raise RuntimeError("Signer key vault contains an invalid TRON address")
            self._private_key(address)

    def _units(self, amount: Decimal) -> int:
        scaled = amount * (Decimal(10) ** self._decimals)
        if scaled != scaled.to_integral_value():
            raise ChainError(
                f"Amount has more than {self._decimals} decimal places"
            )
        return int(scaled)

    def balance(self, address: str) -> Decimal:
        address = address.strip()
        if not self._client.is_address(address):
            raise ChainError("Wallet address is invalid")
        try:
            units = int(self._contract.functions.balanceOf(address))
        except Exception as exc:
            raise ChainError(f"Unable to query TRC20 balance: {exc}") from exc
        return token_amount(Decimal(units) / (Decimal(10) ** self._decimals))

    def trx_balance(self, address: str) -> Decimal:
        address = address.strip()
        if not self._client.is_address(address):
            raise ChainError("Wallet address is invalid")
        try:
            value = self._client.get_account_balance(address)
        except Exception as exc:
            raise ChainError(f"Unable to query TRX balance: {exc}") from exc
        return token_amount(value)

    def sweep(self, source_address: str, amount: Decimal) -> BroadcastResult:
        with self._treasury_lock:
            destination = self._treasury
            if source_address == destination:
                raise ChainError("Source wallet cannot be the treasury wallet")
            if amount <= 0:
                raise ChainError("Withdrawal amount must be greater than zero")
            key = self._private_key(source_address)
            balance_before = self.balance(source_address)
            if amount > balance_before:
                raise ChainError("Withdrawal exceeds the current on-chain token balance")
            units = self._units(amount)
            try:
                transaction = (
                    self._contract.functions.transfer(destination, units)
                    .with_owner(source_address)
                    .fee_limit(self._fee_limit)
                    .build()
                    .sign(key)
                )
                result = transaction.broadcast()
            except Exception as exc:
                raise ChainError(f"Unable to build or broadcast TRC20 transfer: {exc}") from exc
            transaction_hash = str(getattr(result, "txid", "") or transaction.txid)
            if not transaction_hash:
                raise ChainError("TRON node did not return a transaction hash")
            return BroadcastResult(transaction_hash, amount, balance_before, destination)

    def transaction_status(
        self, transaction_hash: str, source_address: str
    ) -> TransactionStatus:
        from tronpy.exceptions import TransactionNotFound

        self._private_key(source_address)
        try:
            info = self._client.get_transaction_info(transaction_hash)
        except TransactionNotFound:
            return TransactionStatus("submitted", None, None)
        except Exception as exc:
            raise ChainError(f"Unable to query TRON transaction: {exc}") from exc
        receipt = info.get("receipt") if isinstance(info, dict) else None
        result = receipt.get("result") if isinstance(receipt, dict) else None
        status = "confirmed" if result in (None, "SUCCESS") else "failed"
        fee_sun = info.get("fee") if isinstance(info, dict) else None
        fee = (
            token_amount(Decimal(str(fee_sun)) / Decimal(1_000_000))
            if fee_sun is not None
            else None
        )
        error = "" if status == "confirmed" else str(result or "TRC20 transfer failed")
        return TransactionStatus(status, self.balance(source_address), fee, error)
