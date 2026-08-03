import asyncio
import json

import httpx
import pytest

from payment_server.deposit_watcher import DepositWatcher, WatcherConfig


@pytest.mark.asyncio
async def test_watcher_delivers_confirmed_trc20_transfer_once():
    address = "TTestAddress111111111111111111111111"
    contract = "TTokenContract11111111111111111111111"
    webhook_payloads = []

    def chain_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/v1/accounts/{address}/transactions/trc20"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "transaction_id": "chain-tx-1",
                        "block_timestamp": 123456,
                        "from": "TSenderAddress11111111111111111111111",
                        "to": address,
                        "value": "1000000000",
                        "token_info": {
                            "address": contract,
                            "symbol": "USDT",
                            "decimals": 6,
                        },
                    }
                ],
                "meta": {},
            },
        )

    def payment_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/webhooks/tron/deposits"
        assert request.headers["X-Webhook-Key"] == "webhook-secret"
        webhook_payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "confirmed",
                "credited": True,
                "duplicate": False,
                "newly_credited": True,
            },
        )

    config = WatcherConfig(
        addresses=(address,),
        contract_address=contract,
        chain_endpoint="https://nile.test",
        chain_network="nile",
        network="tron",
        asset="USDT",
        webhook_url="https://payments.test",
        webhook_key="webhook-secret",
        trongrid_api_key="",
        required_confirmations=1,
        poll_interval_seconds=10,
        lookback_seconds=3600,
        max_pages=1,
    )
    async with (
        httpx.AsyncClient(
            base_url=config.chain_endpoint,
            transport=httpx.MockTransport(chain_handler),
        ) as chain_client,
        httpx.AsyncClient(
            base_url=config.webhook_url,
            transport=httpx.MockTransport(payment_handler),
        ) as payment_client,
    ):
        watcher = DepositWatcher(
            config,
            chain_client=chain_client,
            payment_client=payment_client,
        )
        await watcher.poll_once()
        await watcher.poll_once()

    assert webhook_payloads == [
        {
            "event_id": "tron:chain-tx-1:0",
            "network": "tron",
            "asset": "USDT",
            "address": address,
            "transaction_hash": "chain-tx-1",
            "event_index": 0,
            "amount": "1000",
            "confirmations": 1,
        }
    ]


@pytest.mark.asyncio
async def test_watcher_loads_generated_wallets_from_address_provider():
    address = "TGeneratedAddress1111111111111111111111"
    seen = []

    def chain_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"data": [], "meta": {}})

    config = WatcherConfig(
        addresses=(),
        contract_address="TTokenContract11111111111111111111111",
        chain_endpoint="https://nile.test",
        chain_network="nile",
        network="tron",
        asset="USDT",
        webhook_url="https://payments.test",
        webhook_key="webhook-secret",
        trongrid_api_key="",
        required_confirmations=1,
        poll_interval_seconds=10,
        lookback_seconds=3600,
        max_pages=1,
    )
    async with (
        httpx.AsyncClient(
            base_url=config.chain_endpoint,
            transport=httpx.MockTransport(chain_handler),
        ) as chain_client,
        httpx.AsyncClient(base_url=config.webhook_url) as payment_client,
    ):
        watcher = DepositWatcher(
            config,
            chain_client=chain_client,
            payment_client=payment_client,
            address_provider=lambda: _addresses(address),
        )
        await watcher.poll_once()

    assert seen == [f"/v1/accounts/{address}/transactions/trc20"]


@pytest.mark.asyncio
async def test_watcher_verifies_one_thousand_simultaneous_deposits():
    addresses = tuple(f"T{i:033d}" for i in range(1000))
    contract = "TTokenContract11111111111111111111111"
    delivered: set[str] = set()
    active_chain_requests = 0
    peak_chain_requests = 0
    current_block_requests = 0

    async def chain_handler(request: httpx.Request) -> httpx.Response:
        nonlocal active_chain_requests, peak_chain_requests, current_block_requests
        active_chain_requests += 1
        peak_chain_requests = max(peak_chain_requests, active_chain_requests)
        await asyncio.sleep(0)
        try:
            if request.url.path == "/wallet/getnowblock":
                current_block_requests += 1
                return httpx.Response(
                    200,
                    json={"block_header": {"raw_data": {"number": 119}}},
                )
            if request.url.path == "/wallet/gettransactioninfobyid":
                return httpx.Response(200, json={"blockNumber": 100})

            address = request.url.path.split("/")[3]
            transaction_hash = f"tx-{address}"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "transaction_id": transaction_hash,
                            "event_index": 0,
                            "block_timestamp": 123456,
                            "to": address,
                            "value": "1000000",
                            "token_info": {
                                "address": contract,
                                "symbol": "USDT",
                                "decimals": 6,
                            },
                        }
                    ],
                    "meta": {},
                },
            )
        finally:
            active_chain_requests -= 1

    async def payment_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["confirmations"] == 20
        delivered.add(payload["event_id"])
        await asyncio.sleep(0)
        return httpx.Response(
            200,
            json={
                "status": "confirmed",
                "credited": True,
                "duplicate": False,
                "newly_credited": True,
            },
        )

    config = WatcherConfig(
        addresses=addresses,
        contract_address=contract,
        chain_endpoint="https://nile.test",
        chain_network="nile",
        network="tron",
        asset="USDT",
        webhook_url="https://payments.test",
        webhook_key="webhook-secret",
        trongrid_api_key="",
        required_confirmations=20,
        poll_interval_seconds=10,
        lookback_seconds=3600,
        max_pages=1,
        max_concurrency=40,
        retry_attempts=1,
        retry_base_delay_seconds=0,
    )
    async with (
        httpx.AsyncClient(
            base_url=config.chain_endpoint,
            transport=httpx.MockTransport(chain_handler),
        ) as chain_client,
        httpx.AsyncClient(
            base_url=config.webhook_url,
            transport=httpx.MockTransport(payment_handler),
        ) as payment_client,
    ):
        watcher = DepositWatcher(
            config,
            chain_client=chain_client,
            payment_client=payment_client,
        )
        await watcher.poll_once()
        await watcher.poll_once()

    assert len(delivered) == 1000
    assert current_block_requests == 1
    assert 1 < peak_chain_requests <= config.max_concurrency


@pytest.mark.asyncio
async def test_watcher_isolates_address_failures_and_processes_other_deposits():
    failed_address = "TFailedAddress11111111111111111111111"
    good_address = "TGoodAddress111111111111111111111111"
    contract = "TTokenContract11111111111111111111111"
    delivered = []

    def chain_handler(request: httpx.Request) -> httpx.Response:
        address = request.url.path.split("/")[3]
        if address == failed_address:
            return httpx.Response(503, text="temporary failure")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "transaction_id": "good-tx",
                        "event_index": 0,
                        "block_timestamp": 123456,
                        "to": good_address,
                        "value": "5000000",
                        "token_info": {
                            "address": contract,
                            "symbol": "USDT",
                            "decimals": 6,
                        },
                    }
                ],
                "meta": {},
            },
        )

    def payment_handler(request: httpx.Request) -> httpx.Response:
        delivered.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "confirmed",
                "credited": True,
                "duplicate": False,
                "newly_credited": True,
            },
        )

    config = WatcherConfig(
        addresses=(failed_address, good_address),
        contract_address=contract,
        chain_endpoint="https://nile.test",
        chain_network="nile",
        network="tron",
        asset="USDT",
        webhook_url="https://payments.test",
        webhook_key="webhook-secret",
        trongrid_api_key="",
        required_confirmations=1,
        poll_interval_seconds=10,
        lookback_seconds=3600,
        max_pages=1,
        max_concurrency=2,
        retry_attempts=1,
        retry_base_delay_seconds=0,
    )
    async with (
        httpx.AsyncClient(
            base_url=config.chain_endpoint,
            transport=httpx.MockTransport(chain_handler),
        ) as chain_client,
        httpx.AsyncClient(
            base_url=config.webhook_url,
            transport=httpx.MockTransport(payment_handler),
        ) as payment_client,
    ):
        await DepositWatcher(
            config,
            chain_client=chain_client,
            payment_client=payment_client,
        ).poll_once()

    assert [item["event_id"] for item in delivered] == ["tron:good-tx:0"]


async def _addresses(address):
    return [address]
