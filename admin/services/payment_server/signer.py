from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import httpx

from payment_server.db.repository import money


class SignerError(RuntimeError):
    def __init__(self, message: str, *, uncertain: bool) -> None:
        super().__init__(message)
        self.uncertain = uncertain


@dataclass(frozen=True)
class SignerSweepResult:
    transaction_hash: str
    amount: Decimal
    balance_before: Decimal
    destination_address: str
    network_fee: Optional[Decimal]


@dataclass(frozen=True)
class SignerConfig:
    treasury_address: str
    contract_address: str
    network: str
    asset: str


@dataclass(frozen=True)
class SignerTransactionResult:
    status: str
    balance_after: Optional[Decimal]
    network_fee: Optional[Decimal]
    error_message: str = ""


@dataclass(frozen=True)
class SignerWallet:
    address: str
    network: str
    asset: str


@dataclass(frozen=True)
class SignerWalletBalances:
    token_balance: Decimal
    trx_balance: Decimal
    asset: str


class PaymentSignerClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        *,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = (
            base_url if base_url is not None else os.getenv("PAYMENT_SIGNER_URL", "")
        ).strip().rstrip("/")
        self._api_key = (
            api_key if api_key is not None else os.getenv("PAYMENT_SIGNER_API_KEY", "")
        ).strip()
        self._client = client

    def _configuration(self) -> tuple[str, str]:
        if not self._base_url or not self._api_key:
            raise SignerError(
                "PAYMENT_SIGNER_URL and PAYMENT_SIGNER_API_KEY must be configured",
                uncertain=False,
            )
        return self._base_url, self._api_key

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        base_url, api_key = self._configuration()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(base_url=base_url, timeout=timeout)
        try:
            try:
                response = await client.request(
                    method,
                    path,
                    headers={"X-Signer-Key": api_key},
                    json=json_body,
                    timeout=timeout,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise SignerError(
                    "Unable to determine whether the signer submitted the transaction",
                    uncertain=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise SignerError("Unable to reach the signer", uncertain=True) from exc

            if not response.is_success:
                try:
                    detail = response.json().get("detail")
                except (ValueError, AttributeError):
                    detail = None
                message = str(detail or f"Signer returned HTTP {response.status_code}")
                raise SignerError(
                    message,
                    uncertain=method.upper() == "POST" or response.status_code >= 500,
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise SignerError(
                    "Signer returned invalid JSON",
                    uncertain=method.upper() == "POST",
                ) from exc
            if not isinstance(payload, dict):
                raise SignerError(
                    "Signer returned an unexpected response",
                    uncertain=method.upper() == "POST",
                )
            return payload
        finally:
            if owns_client:
                await client.aclose()

    async def wallet_balances(self, address: str) -> SignerWalletBalances:
        payload = await self._request("GET", f"/v1/wallets/{address}/balance")
        try:
            return SignerWalletBalances(
                token_balance=money(payload.get("balance")),
                trx_balance=money(payload.get("trx_balance") or "0"),
                asset=str(payload.get("asset") or "").strip().upper() or "USDT",
            )
        except (ValueError, ArithmeticError) as exc:
            raise SignerError("Signer returned an invalid balance", uncertain=False) from exc

    async def balance(self, address: str) -> Decimal:
        return (await self.wallet_balances(address)).token_balance

    async def create_wallet(self, request_id: str) -> SignerWallet:
        payload = await self._request(
            "POST",
            "/v1/wallets",
            json_body={"request_id": request_id},
        )
        result = SignerWallet(
            address=str(payload.get("address") or "").strip(),
            network=str(payload.get("network") or "").strip().lower(),
            asset=str(payload.get("asset") or "").strip().upper(),
        )
        if not result.address or not result.network or not result.asset:
            raise SignerError("Signer returned incomplete wallet data", uncertain=True)
        return result

    async def config(self) -> SignerConfig:
        payload = await self._request("GET", "/v1/config")
        result = SignerConfig(
            treasury_address=str(payload.get("treasury_address") or "").strip(),
            contract_address=str(payload.get("contract_address") or "").strip(),
            network=str(payload.get("network") or "").strip(),
            asset=str(payload.get("asset") or "").strip().upper(),
        )
        if not all(
            (
                result.treasury_address,
                result.contract_address,
                result.network,
                result.asset,
            )
        ):
            raise SignerError("Signer returned incomplete configuration", uncertain=False)
        return result

    async def update_treasury(self, treasury_address: str) -> SignerConfig:
        payload = await self._request(
            "PUT",
            "/v1/config/treasury",
            json_body={"treasury_address": treasury_address},
        )
        result = SignerConfig(
            treasury_address=str(payload.get("treasury_address") or "").strip(),
            contract_address=str(payload.get("contract_address") or "").strip(),
            network=str(payload.get("network") or "").strip(),
            asset=str(payload.get("asset") or "").strip().upper(),
        )
        if not all((result.treasury_address, result.contract_address, result.network, result.asset)):
            raise SignerError("Signer returned incomplete configuration", uncertain=False)
        return result

    async def sweep(
        self,
        *,
        sweep_id: int,
        source_address: str,
        amount: Decimal,
    ) -> SignerSweepResult:
        payload = await self._request(
            "POST",
            "/v1/sweeps",
            json_body={
                "sweep_id": str(sweep_id),
                "source_address": source_address,
                "amount": format(amount, "f"),
            },
            timeout=60.0,
        )
        transaction_hash = str(payload.get("transaction_hash") or "").strip()
        destination = str(payload.get("destination_address") or "").strip()
        if not transaction_hash:
            raise SignerError(
                "Signer did not return a transaction hash",
                uncertain=True,
            )
        if not destination:
            raise SignerError(
                "Signer did not return the treasury destination",
                uncertain=True,
            )
        fee = payload.get("network_fee")
        try:
            return SignerSweepResult(
                transaction_hash=transaction_hash,
                amount=money(payload.get("amount")),
                balance_before=money(payload.get("balance_before")),
                destination_address=destination,
                network_fee=money(fee) if fee is not None else None,
            )
        except (ValueError, ArithmeticError) as exc:
            raise SignerError(
                "Signer returned invalid withdrawal amounts",
                uncertain=True,
            ) from exc

    async def transaction(self, transaction_hash: str, source_address: str):
        payload = await self._request(
            "GET",
            f"/v1/transactions/{transaction_hash}?source_address={source_address}",
        )
        balance = payload.get("balance_after")
        fee = payload.get("network_fee")
        try:
            return SignerTransactionResult(
                status=str(payload.get("status") or "submitted"),
                balance_after=money(balance) if balance is not None else None,
                network_fee=money(fee) if fee is not None else None,
                error_message=str(payload.get("error_message") or ""),
            )
        except (ValueError, ArithmeticError) as exc:
            raise SignerError(
                "Signer returned invalid transaction amounts",
                uncertain=False,
            ) from exc
