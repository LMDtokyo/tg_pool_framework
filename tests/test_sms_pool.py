from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from src.api.hero_sms import HeroSmsApiError
from src.api.sms_pool import (
    close_activation,
    fetch_countries,
    fetch_operators,
    get_activation_status,
    fetch_telegram_price,
    request_number,
)


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_fetch_countries_uses_native_success_rate_catalog():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.smspool.net/request/success_rate"
        assert request.content == b"service=Telegram"
        return httpx.Response(
            200,
            json=[
                {
                    "country_id": 1,
                    "country": 1,
                    "name": "United States",
                    "short_name": "US",
                    "success_rate": "100",
                    "price": "0.80",
                },
                {
                    "country_id": 23,
                    "country": 23,
                    "name": "France",
                    "short_name": "FR",
                    "success_rate": "80",
                    "price": "0.10",
                },
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        countries = await fetch_countries("secret-key", client=client)

    assert countries == [
        {
            "id": 1,
            "rus": "United States",
            "eng": "United States",
            "chn": "United States",
            "visible": 1,
            "retry": 0,
        },
        {
            "id": 23,
            "rus": "France",
            "eng": "France",
            "chn": "France",
            "visible": 1,
            "retry": 0,
        },
    ]


@pytest.mark.asyncio
async def test_fetch_telegram_price_uses_native_success_rate_catalog():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json=[
                {
                    "country_id": 1,
                    "name": "United States",
                    "success_rate": "97",
                    "price": "0.80",
                }
            ],
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        price, available = await fetch_telegram_price("secret-key", 1, client=client)

    assert price == Decimal("0.80")
    assert available == 97


@pytest.mark.asyncio
async def test_fetch_countries_reports_provider_errors():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "success": 0,
                "errors": [{"message": "Service does not exist"}],
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HeroSmsApiError, match="Service does not exist"):
            await fetch_countries("secret-key", client=client)


@pytest.mark.asyncio
async def test_fetch_operators_defaults_to_any_operator():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client:
        assert await fetch_operators("secret-key", 1, client=client) == []


@pytest.mark.asyncio
async def test_request_number_uses_native_purchase_endpoint():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.smspool.net/purchase/sms"
        assert request.method == "POST"
        assert request.content == (
            b"key=secret-key&country=1&service=Telegram"
            b"&activation_type=SMS&max_price=0.80"
        )
        return httpx.Response(
            200,
            json={
                "success": 1,
                "number": 15550001111,
                "phonenumber": "5550001111",
                "cc": "1",
                "order_id": "abc123",
                "cost": "0.80",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await request_number(
            "secret-key",
            1,
            "any",
            max_price=Decimal("0.80"),
            client=client,
        )

    assert result["activation_id"] == "abc123"
    assert result["phone_number"] == "15550001111"
    assert result["activation_cost"] == Decimal("0.80")


@pytest.mark.asyncio
async def test_get_activation_status_uses_native_sms_check():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.smspool.net/sms/check"
        assert request.method == "POST"
        assert request.content == b"key=secret-key&orderid=abc123"
        return httpx.Response(200, json={"status": 3, "sms": "12345"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await get_activation_status("secret-key", "abc123", client=client) == (
            "STATUS_OK",
            "12345",
        )


@pytest.mark.asyncio
async def test_close_activation_uses_native_cancel_endpoint():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.smspool.net/sms/cancel"
        assert request.method == "POST"
        assert request.content == b"key=secret-key&orderid=abc123"
        return httpx.Response(200, json={"success": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await close_activation("secret-key", "abc123", cancel=True, client=client)


@pytest.mark.asyncio
async def test_close_activation_ignores_native_finish_call():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client:
        await close_activation("secret-key", "abc123", cancel=False, client=client)
