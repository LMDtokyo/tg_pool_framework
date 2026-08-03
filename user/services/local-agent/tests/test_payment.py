import httpx
import pytest

from tg_pool.api.payment import (
    create_order,
    fetch_balance,
    fetch_catalog,
)


@pytest.mark.asyncio
async def test_payment_client_uses_issued_key_as_bearer_token():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1/balance":
            return httpx.Response(
                200,
                json={
                    "balance": "12.50",
                    "credit_limit": "0",
                    "available_balance": "12.50",
                    "currency": "USD",
                },
            )
        if request.url.path == "/v1/products":
            return httpx.Response(200, json={"items": []})
        return httpx.Response(
            200,
            json={
                "order_id": 1,
                "external_order_id": "order-1",
                "status": "completed",
                "payment_status": "paid",
                "product_id": 7,
                "quantity": 1,
                "unit_price": "3.50",
                "total_amount": "3.50",
                "currency": "USD",
                "items": [],
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://payments.example.test",
    ) as client:
        await fetch_balance("sk_live_customer", client=client)
        await fetch_catalog("sk_live_customer", client=client)
        await create_order(
            "sk_live_customer",
            product_id=7,
            quantity=1,
            external_order_id="order-1",
            client=client,
        )

    assert len(seen) == 3
    assert all(
        request.headers["Authorization"] == "Bearer sk_live_customer"
        for request in seen
    )
    assert all("api_secret" not in request.content.decode("utf-8") for request in seen)
