from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from payment_server.provider import DatamollProvider


pytestmark = pytest.mark.unit


def _product(product_id: int, name: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "product_id": product_id,
        "name": name,
        "price": "2.00",
        "currency": "USD",
        "stock": 5,
        "min_order": 1,
        "max_order": None,
        "category_id": None,
        "category_name": None,
        "description": None,
        "country": "us",
        "image_url": None,
        "content_language": "en",
        "available_languages": ["en"],
        "fallback_applied": False,
        "updated_at": None,
    }
    base.update(overrides)
    return base


def _catalog_page(items: list[dict[str, Any]], *, has_more: bool, next_after_id: int | None = None) -> dict[str, Any]:
    return {
        "partner_id": 1,
        "items": items,
        "limit": 500,
        "has_more": has_more,
        "next_after_id": next_after_id,
        "only_in_stock": True,
        "category_id": None,
        "updated_since": None,
    }


def _order_payload(**overrides: Any) -> dict[str, Any]:
    base = {
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
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _credentials(monkeypatch):
    monkeypatch.setenv("DATAMOLL_PROVIDER_KEY", "public")
    monkeypatch.setenv("DATAMOLL_PROVIDER_SECRET", "private")


def test_missing_credentials_raise_before_any_request():
    import os

    os.environ.pop("DATAMOLL_PROVIDER_KEY", None)
    os.environ.pop("DATAMOLL_PROVIDER_SECRET", None)
    with pytest.raises(RuntimeError, match="DATAMOLL_PROVIDER_KEY"):
        DatamollProvider()._credentials()


@pytest.mark.asyncio
async def test_catalog_paginates_and_keeps_only_telegram_products():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(request.url).startswith("https://datamollcore.com/api/v1/provider/catalog")
        assert request.headers["X-Provider-Key"] == "public:private"
        if calls == 1:
            assert "after_id" not in request.url.params
            return httpx.Response(
                200,
                json=_catalog_page(
                    [_product(1, "Telegram USA"), _product(2, "Facebook USA")],
                    has_more=True,
                    next_after_id=2,
                ),
            )
        assert request.url.params["after_id"] == "2"
        return httpx.Response(
            200,
            json=_catalog_page(
                [_product(3, "Autoreg USA", category_name="Telegram")],
                has_more=False,
            ),
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await DatamollProvider().catalog(http_client=mock_client)

    assert calls == 2
    assert [item["product_id"] for item in result] == [1, 3]


@pytest.mark.asyncio
async def test_catalog_matches_telegram_by_description_and_country_fields():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_catalog_page(
                [
                    _product(10, "USA accounts", description="Registration: tdata export included."),
                    _product(11, "Discord USA"),
                ],
                has_more=False,
            ),
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await DatamollProvider().catalog(http_client=mock_client)

    assert [item["product_id"] for item in result] == [10]


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
        return httpx.Response(201, json=_order_payload())

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await DatamollProvider().create_order(
        product_id=5,
        quantity=2,
        external_order_id="tgpool-order-1",
        http_client=mock_client,
    )

    assert result["order_id"] == 4012
    assert result["items"] == ["account-one", "account-two"]


@pytest.mark.asyncio
async def test_processing_order_is_recovered_by_external_order_id():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                202,
                headers={"Retry-After": "0"},
                json={"error": {"code": "order_processing", "message": "Order processing", "details": None}},
            )
        assert request.method == "GET"
        assert request.url.path.endswith("/orders/by-external-id/tgpool-order-2")
        return httpx.Response(200, json=_order_payload(order_id=4013, external_order_id="tgpool-order-2"))

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await DatamollProvider().create_order(
        product_id=6,
        quantity=1,
        external_order_id="tgpool-order-2",
        http_client=mock_client,
    )

    assert calls == 2
    assert result["order_id"] == 4013


@pytest.mark.asyncio
async def test_provider_error_message_is_preserved():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            402,
            json={"error": {"code": "insufficient_balance", "message": "Not enough partner balance", "details": None}},
        )
    )
    mock_client = httpx.AsyncClient(transport=transport)
    with pytest.raises(Exception, match="Not enough partner balance"):
        await DatamollProvider().create_order(
            product_id=5,
            quantity=1,
            external_order_id="tgpool-order-3",
            http_client=mock_client,
        )
