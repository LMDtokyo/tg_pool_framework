from decimal import Decimal

import httpx
import pytest

from payment_server.signer import PaymentSignerClient, SignerError


@pytest.mark.asyncio
async def test_signer_client_authenticates_and_parses_sweep_flow():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1/config":
            return httpx.Response(
                200,
                json={
                    "treasury_address": "TTreasury",
                    "contract_address": "TContract",
                    "network": "mainnet",
                    "asset": "USDT",
                },
            )
        if request.url.path == "/v1/config/treasury":
            return httpx.Response(
                200,
                json={
                    "treasury_address": "TUpdatedTreasury",
                    "contract_address": "TContract",
                    "network": "mainnet",
                    "asset": "USDT",
                },
            )
        if request.url.path == "/v1/wallets":
            return httpx.Response(
                200,
                json={
                    "address": "TGenerated",
                    "network": "mainnet",
                    "asset": "USDT",
                },
            )
        if request.url.path.endswith("/balance"):
            return httpx.Response(
                200,
                json={
                    "address": "TSource",
                    "balance": "12.5",
                    "asset": "USDT",
                    "trx_balance": "987.455",
                },
            )
        if request.url.path == "/v1/sweeps":
            return httpx.Response(
                200,
                json={
                    "sweep_id": "4",
                    "transaction_hash": "tx-4",
                    "amount": "5",
                    "balance_before": "12.5",
                    "destination_address": "TTreasury",
                },
            )
        return httpx.Response(
            200,
            json={
                "status": "confirmed",
                "balance_after": "7.5",
                "network_fee": "8",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://signer.test",
    ) as http:
        client = PaymentSignerClient(
            "https://signer.test",
            "internal-secret",
            client=http,
        )
        assert (await client.config()).treasury_address == "TTreasury"
        assert (await client.update_treasury("TUpdatedTreasury")).treasury_address == "TUpdatedTreasury"
        wallet = await client.create_wallet("telegram:123")
        assert wallet.address == "TGenerated"
        assert await client.balance("TSource") == Decimal("12.50000000")
        balances = await client.wallet_balances("TSource")
        assert balances.token_balance == Decimal("12.50000000")
        assert balances.trx_balance == Decimal("987.45500000")
        sweep = await client.sweep(
            sweep_id=4,
            source_address="TSource",
            amount=Decimal("5"),
        )
        assert sweep.transaction_hash == "tx-4"
        status = await client.transaction("tx-4", "TSource")
        assert status.status == "confirmed"
        assert status.balance_after == Decimal("7.50000000")

    assert all(request.headers["X-Signer-Key"] == "internal-secret" for request in seen)
    assert seen[-1].url.params["source_address"] == "TSource"


@pytest.mark.asyncio
async def test_signer_post_error_is_treated_as_uncertain():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(422, json={"detail": "resource failure"})
        ),
        base_url="https://signer.test",
    ) as http:
        client = PaymentSignerClient(
            "https://signer.test",
            "internal-secret",
            client=http,
        )
        with pytest.raises(SignerError) as raised:
            await client.sweep(
                sweep_id=4,
                source_address="TSource",
                amount=Decimal("5"),
            )
    assert raised.value.uncertain
