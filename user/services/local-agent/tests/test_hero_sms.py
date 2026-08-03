from __future__ import annotations

import httpx
import pytest

from decimal import Decimal

from tg_pool.api.hero_sms import (
    HeroSmsApiError,
    fetch_balance,
    fetch_countries,
    fetch_operators,
    fetch_telegram_offers,
    fetch_telegram_price,
    get_activation_status,
    request_number_v2,
)


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_fetch_countries_sends_key_and_returns_only_visible_countries():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["action"] == "getCountries"
        assert request.url.params["api_key"] == "secret-key"
        return httpx.Response(
            200,
            json={
                "2": {"id": 2, "rus": "Казахстан", "eng": "Kazakhstan", "chn": "哈萨克斯坦", "visible": 1, "retry": 1},
                "1": {"id": 1, "rus": "Украина", "eng": "Ukraine", "chn": "乌克兰", "visible": 0, "retry": 1},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        countries = await fetch_countries(" secret-key ", client=client)

    assert countries == [
        {
            "id": 2,
            "rus": "Казахстан",
            "eng": "Kazakhstan",
            "chn": "哈萨克斯坦",
            "visible": 1,
            "retry": 1,
        }
    ]


@pytest.mark.asyncio
async def test_fetch_countries_rejects_unexpected_response():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=[]))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HeroSmsApiError, match="no available"):
            await fetch_countries("secret-key", client=client)


@pytest.mark.asyncio
async def test_fetch_countries_requires_api_key():
    with pytest.raises(ValueError, match="API key"):
        await fetch_countries("  ")


@pytest.mark.asyncio
async def test_fetch_balance_sends_key_and_parses_legacy_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["action"] == "getBalance"
        assert request.url.params["api_key"] == "secret-key"
        return httpx.Response(200, text="ACCESS_BALANCE:123.45")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        balance = await fetch_balance("secret-key", client=client)

    assert balance == Decimal("123.45")


@pytest.mark.asyncio
async def test_fetch_balance_reports_rejected_key_without_exposing_it():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text="BAD_KEY"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HeroSmsApiError, match="rejected the API key") as exc_info:
            await fetch_balance("secret-key", client=client)

    assert "secret-key" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_balance_rejects_invalid_amount():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, text="ACCESS_BALANCE:not-a-number")
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HeroSmsApiError, match="invalid balance"):
            await fetch_balance("secret-key", client=client)


@pytest.mark.asyncio
async def test_fetch_operators_sends_country_and_filters_values():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["action"] == "getOperators"
        assert request.url.params["api_key"] == "secret-key"
        assert request.url.params["country"] == "6"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "countryOperators": {
                    "6": ["any", "tele2", " tele2 ", "beeline", "", None]
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        operators = await fetch_operators("secret-key", 6, client=client)

    assert operators == ["any", "tele2", "beeline"]


@pytest.mark.asyncio
async def test_fetch_operators_accepts_empty_country_list():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={"status": "success", "countryOperators": {"6": []}},
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert await fetch_operators("secret-key", 6, client=client) == []


@pytest.mark.asyncio
async def test_fetch_operators_reports_rejected_key_safely():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text="BAD_KEY"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HeroSmsApiError, match="rejected the API key") as exc_info:
            await fetch_operators("secret-key", 6, client=client)

    assert "secret-key" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_telegram_price_sends_service_and_parses_cost():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["action"] == "getPrices"
        assert request.url.params["service"] == "tg"
        assert request.url.params["country"] == "6"
        assert "operator" not in request.url.params
        assert request.url.params["api_key"] == "secret-key"
        return httpx.Response(
            200,
            json={"6": {"tg": {"cost": "0.006", "count": 123}}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        price, available = await fetch_telegram_price("secret-key", 6, client=client)

    assert price == Decimal("0.006")
    assert available == 123


@pytest.mark.asyncio
async def test_fetch_telegram_price_accepts_unavailable_country():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={}))
    async with httpx.AsyncClient(transport=transport) as client:
        assert await fetch_telegram_price("secret-key", 6, client=client) == (None, 0)


@pytest.mark.asyncio
async def test_fetch_telegram_price_rejects_invalid_cost():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={"6": {"tg": {"cost": "not-a-price", "count": 1}}},
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HeroSmsApiError, match="invalid Telegram price"):
            await fetch_telegram_price("secret-key", 6, client=client)


@pytest.mark.asyncio
async def test_fetch_telegram_offers_parses_price_map():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://hero-sms.com/api/v1/activations/offers")
        assert request.url.params["services"] == "tg"
        assert request.url.params["countries"] == "43"
        assert request.headers["Authorization"] == "ApiKey secret-key"
        return httpx.Response(
            200,
            json={
                "data": {
                    "tg": {
                        "43": {
                            "prices": {
                                "default": 1.1,
                                "retail": 1.1,
                                "min": 1.1,
                            },
                            "counts": {
                                "total": 3118,
                                "physical": 100,
                                "defaultPrice": 0,
                            },
                            "map": {
                                "1.1000": 2349,
                                "1.3229": 2767,
                                "2.6838": 3118,
                            },
                        }
                    }
                },
                "meta": {},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = await fetch_telegram_offers("secret-key", 43, client=client)

    assert catalog["price"] == Decimal("1.1000")
    assert catalog["available"] == 3118
    assert catalog["offers"] == [
        {"price": Decimal("1.1000"), "available": 2349},
        {"price": Decimal("1.3229"), "available": 2767},
        {"price": Decimal("2.6838"), "available": 3118},
    ]


@pytest.mark.asyncio
async def test_fetch_telegram_offers_recommends_first_stocked_tier():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "data": {
                    "tg": {
                        "32": {
                            "prices": {"default": 0.75, "retail": 0.825, "min": 0.825},
                            "counts": {"total": 1142, "physical": 189, "defaultPrice": 0},
                            "map": {
                                "0.8250": 0,
                                "1.0742": 110,
                                "1.3229": 276,
                            },
                        }
                    }
                }
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        catalog = await fetch_telegram_offers("secret-key", 32, client=client)

    assert catalog["price"] == Decimal("1.0742")
    assert catalog["available"] == 1142
    assert len(catalog["offers"]) == 3


@pytest.mark.asyncio
async def test_fetch_telegram_offers_accepts_missing_country():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"data": {"tg": {}}, "meta": {}})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        catalog = await fetch_telegram_offers("secret-key", 32, client=client)

    assert catalog == {"price": None, "available": 0, "offers": []}


@pytest.mark.asyncio
async def test_request_number_v2_uses_fixed_price_stub_purchase():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.params["action"] == "getNumberV2"
        assert request.url.params["service"] == "tg"
        assert request.url.params["country"] == "32"
        assert request.url.params["operator"] == "any"
        assert request.url.params["maxPrice"] == "1.0742"
        assert request.url.params["fixedPrice"] == "true"
        assert request.url.params["api_key"] == "secret-key"
        return httpx.Response(
            200,
            json={
                "activationId": "635468024",
                "phoneNumber": "40755111222",
                "activationCost": 1.0742,
                "currency": 840,
                "activationOperator": "tele2",
                "canGetAnotherSms": True,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await request_number_v2(
            "secret-key", 32, "any", max_price=Decimal("1.0742"), client=client
        )

    assert result["activation_id"] == "635468024"
    assert result["phone_number"] == "40755111222"
    assert result["activation_cost"] == Decimal("1.0742")
    assert result["operator"] == "tele2"


@pytest.mark.asyncio
async def test_request_number_v2_maps_http_404_to_no_numbers():
    transport = httpx.MockTransport(lambda _: httpx.Response(404, text="NOT_FOUND"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HeroSmsApiError, match="no matching numbers"):
            await request_number_v2(
                "secret-key", 6, "any", max_price=Decimal("1.0742"), client=client
            )


@pytest.mark.asyncio
async def test_get_activation_status_parses_received_code():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, text="STATUS_OK:12345")
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert await get_activation_status(
            "secret-key", "635468024", client=client
        ) == ("STATUS_OK", "12345")
