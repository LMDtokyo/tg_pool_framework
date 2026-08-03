from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from payment_server.datamoll_client import (
    DatamollApiError,
    create_order_with_recovery,
    fetch_balance,
    fetch_telegram_catalog,
)


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_fetch_balance_uses_provider_credentials_header():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://datamollcore.com/api/v1/provider/balance"
        assert request.headers["X-Provider-Key"] == "public:private"
        assert request.headers["User-Agent"] == "tg-pool-framework/1.0"
        return httpx.Response(
            200,
            json={
                "partner_id": 72,
                "balance": "10.00",
                "credit_limit": "2.00",
                "available_balance": "12.00",
                "currency": "USD",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_balance("public", "private", client=client)

    assert result == {
        "balance": "10.00",
        "credit_limit": "2.00",
        "available_balance": "12.00",
        "currency": "USD",
    }


@pytest.mark.asyncio
async def test_catalog_paginates_and_keeps_only_telegram_products():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["limit"] == "500"
        assert request.url.params["only_in_stock"] == "true"
        assert request.url.params["language"] == "en"
        if calls == 1:
            assert "after_id" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"product_id": 1, "name": "Telegram USA"},
                        {"product_id": 2, "name": "Facebook USA"},
                    ],
                    "has_more": True,
                    "next_after_id": 2,
                },
            )
        assert request.url.params["after_id"] == "2"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "product_id": 3,
                        "name": "Autoreg USA",
                        "category_name": "Telegram",
                    }
                ],
                "has_more": False,
                "next_after_id": None,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_telegram_catalog("public", "private", client=client)

    assert [item["product_id"] for item in result] == [1, 3]


@pytest.mark.asyncio
async def test_catalog_reads_nested_pagination_and_structured_telegram_fields():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["limit"] == "500"
        if calls == 1:
            assert "after_id" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "product_id": 10,
                            "name": "USA accounts",
                            "category": {"slug": "telegram-ready"},
                            "description": "Registration country: United States.",
                        },
                        {
                            "product_id": 11,
                            "name": "Discord USA",
                            "category": {"slug": "discord"},
                        },
                    ],
                    "pagination": {
                        "has_more": True,
                        "next_after_id": "11",
                    },
                },
            )
        assert request.url.params["after_id"] == "11"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "product_id": 12,
                        "name": "Canada accounts",
                        "tags": ["tdata", "aged"],
                    }
                ],
                "pagination": {"has_more": False},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_telegram_catalog("public", "private", client=client)

    assert calls == 2
    assert [item["product_id"] for item in result] == [10, 12]


@pytest.mark.asyncio
async def test_catalog_uses_last_product_id_when_has_more_lacks_cursor():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "items": [{"product_id": 20, "name": "Telegram USA"}],
                    "has_more": True,
                },
            )
        assert request.url.params["after_id"] == "20"
        return httpx.Response(
            200,
            json={
                "items": [{"product_id": 21, "name": "Telegram Canada"}],
                "has_more": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_telegram_catalog("public", "private", client=client)

    assert calls == 2
    assert [item["product_id"] for item in result] == [20, 21]


@pytest.mark.asyncio
async def test_create_order_uses_stable_idempotency_identity():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://datamollcore.com/api/v1/provider/orders"
        assert request.headers["Idempotency-Key"] == "tgpool-order-1"
        assert json.loads(request.content) == {
            "product_id": 5,
            "quantity": 2,
            "external_order_id": "tgpool-order-1",
        }
        return httpx.Response(
            201,
            json={
                "order_id": 4012,
                "external_order_id": "tgpool-order-1",
                "status": "fulfilled",
                "payment_status": "paid",
                "product_id": 5,
                "quantity": 2,
                "unit_price": "10.00",
                "total_amount": "20.00",
                "currency": "USD",
                "items": ["account-one", "account-two"],
                "created_at": "2026-04-13T08:10:00Z",
                "reused_existing": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await create_order_with_recovery(
            "public",
            "private",
            product_id=5,
            quantity=2,
            external_order_id="tgpool-order-1",
            client=client,
        )

    assert result["order_id"] == 4012
    assert result["items"] == ["account-one", "account-two"]


@pytest.mark.asyncio
async def test_processing_order_is_recovered_by_external_order_id():
    calls = 0

    async def no_sleep(_: float) -> None:
        return None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                202,
                headers={"Retry-After": "0"},
                json={
                    "error": {
                        "code": "order_processing",
                        "message": "Order processing",
                        "details": None,
                    }
                },
            )
        assert request.method == "GET"
        assert request.url.path.endswith("/orders/by-external-id/tgpool-order-2")
        return httpx.Response(
            200,
            json={
                "order_id": 4013,
                "external_order_id": "tgpool-order-2",
                "status": "fulfilled",
                "payment_status": "paid",
                "product_id": 6,
                "quantity": 1,
                "unit_price": "8.00",
                "total_amount": "8.00",
                "currency": "USD",
                "items": ["account"],
                "created_at": "2026-04-13T08:10:00Z",
                "reused_existing": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await create_order_with_recovery(
            "public",
            "private",
            product_id=6,
            quantity=1,
            external_order_id="tgpool-order-2",
            client=client,
            recovery_delay_sec=0,
            sleep_func=no_sleep,
        )

    assert calls == 2
    assert result["order_id"] == 4013


@pytest.mark.asyncio
async def test_provider_error_message_is_preserved():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            402,
            json={
                "error": {
                    "code": "insufficient_balance",
                    "message": "Not enough partner balance",
                    "details": None,
                }
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(DatamollApiError, match="Not enough partner balance"):
            await create_order_with_recovery(
                "public",
                "private",
                product_id=5,
                quantity=1,
                external_order_id="tgpool-order-3",
                client=client,
            )


