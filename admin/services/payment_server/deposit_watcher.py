"""Poll TRON for inbound TRC20 deposits and submit payment webhooks.

Run separately from the payment API:
    python -m payment_server.deposit_watcher
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from dotenv import load_dotenv

from payment_server.db.engine import build_session_factory_from_env
from payment_server.db.repository import PaymentRepository

logger = logging.getLogger("payment_server.deposit_watcher")

_ENDPOINTS = {
    "mainnet": "https://api.trongrid.io",
    "nile": "https://nile.trongrid.io",
    "shasta": "https://api.shasta.trongrid.io",
}


@dataclass(frozen=True)
class WatcherConfig:
    addresses: tuple[str, ...]
    contract_address: str
    chain_endpoint: str
    chain_network: str
    network: str
    asset: str
    webhook_url: str
    webhook_key: str
    trongrid_api_key: str
    required_confirmations: int
    poll_interval_seconds: float
    lookback_seconds: int
    max_pages: int
    max_concurrency: int = 50
    retry_attempts: int = 3
    retry_base_delay_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> "WatcherConfig":
        addresses = tuple(
            address.strip()
            for address in os.getenv("PAYMENT_DEPOSIT_ADDRESSES", "").split(",")
            if address.strip()
        )
        chain_network = os.getenv("PAYMENT_CHAIN_NETWORK", "mainnet").strip().lower()
        endpoint = os.getenv("PAYMENT_TRON_HTTP_ENDPOINT", "").strip()
        endpoint = endpoint or _ENDPOINTS.get(chain_network, "")
        config = cls(
            addresses=addresses,
            contract_address=os.getenv("PAYMENT_TRC20_CONTRACT", "").strip(),
            chain_endpoint=endpoint.rstrip("/"),
            chain_network=chain_network,
            network=os.getenv("PAYMENT_NETWORK", "tron").strip().lower(),
            asset=os.getenv("PAYMENT_ASSET", "USDT").strip().upper(),
            webhook_url=os.getenv(
                "PAYMENT_PUBLIC_URL", "http://127.0.0.1:8200"
            ).rstrip("/"),
            webhook_key=os.getenv("PAYMENT_WEBHOOK_KEY", "").strip(),
            trongrid_api_key=os.getenv("TRONGRID_API_KEY", "").strip(),
            required_confirmations=max(
                1, int(os.getenv("PAYMENT_REQUIRED_CONFIRMATIONS", "20"))
            ),
            poll_interval_seconds=max(
                1.0, float(os.getenv("PAYMENT_DEPOSIT_POLL_INTERVAL_SECONDS", "10"))
            ),
            lookback_seconds=max(
                60, int(os.getenv("PAYMENT_DEPOSIT_LOOKBACK_SECONDS", "604800"))
            ),
            max_pages=max(1, int(os.getenv("PAYMENT_DEPOSIT_MAX_PAGES", "10"))),
            max_concurrency=max(
                1, int(os.getenv("PAYMENT_DEPOSIT_MAX_CONCURRENCY", "50"))
            ),
            retry_attempts=max(
                1, int(os.getenv("PAYMENT_DEPOSIT_RETRY_ATTEMPTS", "3"))
            ),
            retry_base_delay_seconds=max(
                0.0,
                float(
                    os.getenv(
                        "PAYMENT_DEPOSIT_RETRY_BASE_DELAY_SECONDS", "0.5"
                    )
                ),
            ),
        )
        if not config.contract_address:
            raise RuntimeError("PAYMENT_TRC20_CONTRACT must be configured")
        if not config.chain_endpoint:
            raise RuntimeError("PAYMENT_TRON_HTTP_ENDPOINT must be configured")
        if not config.webhook_key:
            raise RuntimeError("PAYMENT_WEBHOOK_KEY must be configured")
        return config


@dataclass(frozen=True)
class Trc20Transfer:
    transaction_hash: str
    event_index: int
    to_address: str
    amount: str
    block_timestamp: int


class DepositWatcher:
    def __init__(
        self,
        config: WatcherConfig,
        *,
        chain_client: httpx.AsyncClient,
        payment_client: httpx.AsyncClient,
        address_provider: Callable[[], Awaitable[list[str]]] | None = None,
    ) -> None:
        self.config = config
        self.chain_client = chain_client
        self.payment_client = payment_client
        self.address_provider = address_provider
        self._delivered_confirmations: dict[tuple[str, int], int] = {}
        self._chain_slots = asyncio.Semaphore(config.max_concurrency)
        self._payment_slots = asyncio.Semaphore(config.max_concurrency)

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a request with bounded exponential retry for transient failures."""
        retryable_statuses = {408, 425, 429, 500, 502, 503, 504}
        for attempt in range(self.config.retry_attempts):
            response: httpx.Response | None = None
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code not in retryable_statuses:
                    return response
                if attempt + 1 >= self.config.retry_attempts:
                    return response
            except httpx.TransportError:
                if attempt + 1 >= self.config.retry_attempts:
                    raise

            delay = self.config.retry_base_delay_seconds * (2**attempt)
            if response is not None:
                retry_after = response.headers.get("Retry-After", "").strip()
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    pass
                await response.aclose()
            if delay:
                await asyncio.sleep(min(delay, 30.0))

        raise RuntimeError("unreachable retry loop")

    async def _inbound_transfers(
        self, address: str, *, min_timestamp: int
    ) -> list[Trc20Transfer]:
        transfers: list[Trc20Transfer] = []
        fingerprint: str | None = None
        occurrences: defaultdict[str, int] = defaultdict(int)

        for _ in range(self.config.max_pages):
            params: dict[str, Any] = {
                "only_confirmed": "true",
                "only_to": "true",
                "contract_address": self.config.contract_address,
                "min_timestamp": min_timestamp,
                "order_by": "block_timestamp,asc",
                "limit": 200,
            }
            if fingerprint:
                params["fingerprint"] = fingerprint
            response = await self._request(
                self.chain_client,
                "GET",
                f"/v1/accounts/{address}/transactions/trc20",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("data", []):
                token = item.get("token_info") or {}
                contract = str(token.get("address") or token.get("tokenId") or "")
                to_address = str(item.get("to") or item.get("to_address") or "")
                if contract != self.config.contract_address or to_address != address:
                    continue
                transaction_hash = str(
                    item.get("transaction_id") or item.get("transaction_hash") or ""
                )
                if not transaction_hash:
                    continue
                fallback_index = occurrences[transaction_hash]
                occurrences[transaction_hash] += 1
                event_index = int(
                    item.get("event_index", item.get("log_index", fallback_index))
                )
                decimals = int(token.get("decimals", token.get("tokenDecimal", 0)))
                raw_value = Decimal(str(item.get("value", item.get("quant", "0"))))
                amount = raw_value / (Decimal(10) ** decimals)
                if amount <= 0:
                    continue
                transfers.append(
                    Trc20Transfer(
                        transaction_hash=transaction_hash,
                        event_index=event_index,
                        to_address=to_address,
                        amount=format(amount, "f"),
                        block_timestamp=int(item.get("block_timestamp", 0)),
                    )
                )
            fingerprint = str((payload.get("meta") or {}).get("fingerprint") or "")
            if not fingerprint:
                break
        return transfers

    async def _current_block(self) -> int:
        current_response = await self._request(
            self.chain_client,
            "POST",
            "/wallet/getnowblock",
            json={"visible": True},
        )
        current_response.raise_for_status()
        return int(
            current_response.json()["block_header"]["raw_data"]["number"]
        )

    async def _confirmations(
        self, transaction_hash: str, *, current_block: int
    ) -> int:
        info_response = await self._request(
            self.chain_client,
            "POST",
            "/wallet/gettransactioninfobyid",
            json={"value": transaction_hash, "visible": True},
        )
        info_response.raise_for_status()
        transaction_block = int(info_response.json()["blockNumber"])
        return max(0, current_block - transaction_block + 1)

    async def _deliver(
        self, transfer: Trc20Transfer, *, confirmations: int
    ) -> bool:
        response = await self._request(
            self.payment_client,
            "POST",
            "/webhooks/tron/deposits",
            headers={"X-Webhook-Key": self.config.webhook_key},
            json={
                "event_id": (
                    f"tron:{transfer.transaction_hash}:{transfer.event_index}"
                ),
                "network": self.config.network,
                "asset": self.config.asset,
                "address": transfer.to_address,
                "transaction_hash": transfer.transaction_hash,
                "event_index": transfer.event_index,
                "amount": transfer.amount,
                "confirmations": confirmations,
            },
        )
        if response.is_error:
            logger.warning(
                "Deposit webhook rejected %s:%s with HTTP %s: %s",
                transfer.transaction_hash,
                transfer.event_index,
                response.status_code,
                response.text,
            )
            return False
        result = response.json()
        logger.info(
            "Deposit %s:%s amount=%s %s confirmations=%s status=%s duplicate=%s",
            transfer.transaction_hash,
            transfer.event_index,
            transfer.amount,
            self.config.asset,
            confirmations,
            result.get("status"),
            result.get("duplicate"),
        )
        return True

    async def poll_once(self) -> None:
        min_timestamp = int(
            (time.time() - self.config.lookback_seconds) * 1000
        )
        addresses = set(self.config.addresses)
        if self.address_provider is not None:
            addresses.update(await self.address_provider())

        async def load_address(address: str) -> list[Trc20Transfer]:
            async with self._chain_slots:
                return await self._inbound_transfers(
                    address, min_timestamp=min_timestamp
                )

        address_list = sorted(addresses)
        loaded = await asyncio.gather(
            *(load_address(address) for address in address_list),
            return_exceptions=True,
        )
        transfers_by_key: dict[tuple[str, int], Trc20Transfer] = {}
        failures = 0
        for address, result in zip(address_list, loaded):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                failures += 1
                logger.error(
                    "Unable to scan deposit address %s: %s", address, result
                )
                continue
            for transfer in result:
                key = (transfer.transaction_hash, transfer.event_index)
                existing = transfers_by_key.get(key)
                if existing is not None and existing != transfer:
                    logger.error(
                        "Conflicting chain data for deposit %s:%s",
                        transfer.transaction_hash,
                        transfer.event_index,
                    )
                    continue
                transfers_by_key[key] = transfer

        transfers = [
            transfer
            for key, transfer in transfers_by_key.items()
            if self._delivered_confirmations.get(key)
            != self.config.required_confirmations
        ]
        if not transfers:
            if failures:
                logger.warning(
                    "Deposit poll completed with %s/%s address scan failures",
                    failures,
                    len(address_list),
                )
            return

        transaction_hashes = sorted(
            {transfer.transaction_hash for transfer in transfers}
        )
        confirmation_cache: dict[str, int] = {}
        if self.config.required_confirmations == 1:
            confirmation_cache = {
                transaction_hash: 1 for transaction_hash in transaction_hashes
            }
        else:
            async with self._chain_slots:
                current_block = await self._current_block()

            async def load_confirmations(transaction_hash: str) -> int:
                async with self._chain_slots:
                    return await self._confirmations(
                        transaction_hash, current_block=current_block
                    )

            confirmation_results = await asyncio.gather(
                *(
                    load_confirmations(transaction_hash)
                    for transaction_hash in transaction_hashes
                ),
                return_exceptions=True,
            )
            for transaction_hash, result in zip(
                transaction_hashes, confirmation_results
            ):
                if isinstance(result, asyncio.CancelledError):
                    raise result
                if isinstance(result, BaseException):
                    failures += 1
                    logger.error(
                        "Unable to verify confirmations for %s: %s",
                        transaction_hash,
                        result,
                    )
                    continue
                confirmation_cache[transaction_hash] = min(
                    result, self.config.required_confirmations
                )

        async def deliver_transfer(transfer: Trc20Transfer) -> None:
            confirmations = confirmation_cache.get(transfer.transaction_hash)
            if confirmations is None:
                return
            key = (transfer.transaction_hash, transfer.event_index)
            if self._delivered_confirmations.get(key) == confirmations:
                return
            async with self._payment_slots:
                delivered = await self._deliver(
                    transfer, confirmations=confirmations
                )
            if delivered:
                self._delivered_confirmations[key] = confirmations

        delivery_results = await asyncio.gather(
            *(deliver_transfer(transfer) for transfer in transfers),
            return_exceptions=True,
        )
        for transfer, result in zip(transfers, delivery_results):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                failures += 1
                logger.error(
                    "Unable to deliver deposit %s:%s: %s",
                    transfer.transaction_hash,
                    transfer.event_index,
                    result,
                )

        if failures:
            logger.warning(
                "Deposit poll completed with %s isolated failure(s); "
                "failed items will be retried on the next poll",
                failures,
            )

    async def run(self) -> None:
        logger.info(
            "Watching database wallets plus %s configured %s address(es) on %s "
            "for contract %s",
            len(self.config.addresses),
            self.config.asset,
            self.config.chain_network,
            self.config.contract_address,
        )
        while True:
            try:
                await self.poll_once()
            except Exception:
                logger.exception("Deposit polling failed")
            await asyncio.sleep(self.config.poll_interval_seconds)


async def run() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    config = WatcherConfig.from_env()
    headers = (
        {"TRON-PRO-API-KEY": config.trongrid_api_key}
        if config.trongrid_api_key
        else {}
    )
    session_factory = build_session_factory_from_env()
    repository = PaymentRepository(
        session_factory,
        network=config.network,
        asset=config.asset,
    )
    try:
        async with (
            httpx.AsyncClient(
                base_url=config.chain_endpoint,
                headers=headers,
                timeout=30.0,
            ) as chain_client,
            httpx.AsyncClient(base_url=config.webhook_url, timeout=20.0) as payment_client,
        ):
            await DepositWatcher(
                config,
                chain_client=chain_client,
                payment_client=payment_client,
                address_provider=repository.wallet_addresses,
            ).run()
    finally:
        await session_factory.kw["bind"].dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(name)s %(message)s",
    )
    asyncio.run(run())
