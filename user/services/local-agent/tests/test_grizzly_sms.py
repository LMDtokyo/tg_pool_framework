from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from tg_pool.api.grizzly_sms import (
    close_activation,
    fetch_balance,
    fetch_operators,
    fetch_telegram_price,
    request_number_v2,
)
from tg_pool.api.hero_sms import HeroSmsApiError, get_activation_status


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_balance_uses_grizzly_endpoint_and_documented_action():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(
            "https://api.grizzlysms.com/stubs/handler_api.php?"
        )
        assert request.url.params["api_key"] == "secret"
        assert request.url.params["action"] == "getBalance"
        return httpx.Response(200, text="ACCESS_BALANCE:12.34")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_balance(" secret ", client=client) == Decimal("12.34")


@pytest.mark.asyncio
async def test_price_requests_telegram_for_selected_country():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["action"] == "getPrices"
        assert request.url.params["service"] == "tg"
        assert request.url.params["country"] == "2"
        return httpx.Response(200, json={"2": {"tg": {"cost": 1.25, "count": 7}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await fetch_telegram_price("secret", 2, client=client) == (
            Decimal("1.25"),
            7,
        )


@pytest.mark.asyncio
async def test_number_purchase_uses_documented_v2_parameters_and_parses_result():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["action"] == "getNumberV2"
        assert request.url.params["service"] == "tg"
        assert request.url.params["country"] == "2"
        assert request.url.params["maxPrice"] == "1.25"
        assert "operator" not in request.url.params
        return httpx.Response(
            200,
            json={
                "activationId": 38496653,
                "phoneNumber": "66846426435",
                "activationCost": 1.2,
                "currency": 840,
                "canGetAnotherSms": "1",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await request_number_v2(
            "secret", 2, "any", max_price=Decimal("1.25"), client=client
        )

    assert result["activation_id"] == "38496653"
    assert result["phone_number"] == "66846426435"
    assert result["activation_cost"] == Decimal("1.2")
    assert result["can_get_another_sms"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cancel", "expected_status", "response"),
    [(True, "8", "ACCESS_CANCEL"), (False, "6", "ACCESS_ACTIVATION")],
)
async def test_activation_close_uses_documented_set_status(
    cancel: bool, expected_status: str, response: str
):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["action"] == "setStatus"
        assert request.url.params["status"] == expected_status
        assert request.url.params["id"] == "38496653"
        return httpx.Response(200, text=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await close_activation("secret", "38496653", cancel=cancel, client=client)


@pytest.mark.asyncio
async def test_grizzly_has_no_undocumented_operator_lookup():
    assert await fetch_operators("secret", 2) == []
    with pytest.raises(ValueError, match="API key"):
        await fetch_operators(" ", 2)


@pytest.mark.asyncio
async def test_number_purchase_maps_documented_errors():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text="NO_NUMBERS"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HeroSmsApiError, match="no matching numbers"):
            await request_number_v2("secret", 2, "any", client=client)


@pytest.mark.asyncio
async def test_status_accepts_documented_wait_retry_with_last_code():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, text="STATUS_WAIT_RETRY:12345")
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert await get_activation_status(
            "secret",
            "38496653",
            api_url="https://api.grizzlysms.com/stubs/handler_api.php",
            provider_name="GrizzlySMS",
            client=client,
        ) == ("STATUS_WAIT_RETRY", None)
