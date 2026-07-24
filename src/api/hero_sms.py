from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx


HERO_SMS_API_URL = "https://hero-sms.com/stubs/handler_api.php"
HERO_SMS_OFFERS_URL = "https://hero-sms.com/api/v1/activations/offers"


class HeroSmsApiError(RuntimeError):
    """Raised when Hero SMS cannot provide a valid countries response."""


def _provider_error(
    payload: str,
    operation: str,
    *,
    provider_name: str = "Hero SMS",
) -> HeroSmsApiError:
    error_messages = {
        "BAD_KEY": f"{provider_name} rejected the API key",
        "NO_KEY": f"{provider_name} API key is required",
        "BAD_ACTION": f"{provider_name} rejected the {operation} operation",
        "ERROR_SQL": f"{provider_name} could not retrieve {operation}",
        "BAD_OPERATOR": f"{provider_name} rejected the selected operator",
        "WRONG_OPERATOR": f"{provider_name} rejected the selected operator",
        "NO_NUMBERS": f"{provider_name} has no matching numbers available",
        "NO_BALANCE": f"{provider_name} balance is insufficient",
        "MAX_PRICE_EXCEEDED": f"{provider_name} price now exceeds the displayed maximum",
        "WRONG_SERVICE": f"{provider_name} rejected the selected service",
        "BAD_SERVICE": f"{provider_name} rejected the selected service",
    }
    return HeroSmsApiError(
        error_messages.get(payload, f"{provider_name} returned an unexpected {operation} response")
    )


def _request_params(
    params: dict[str, Any],
    provider_params: dict[str, Any] | None,
) -> dict[str, Any]:
    if not provider_params:
        return params
    return {**params, **provider_params}


async def fetch_balance(
    api_key: str,
    *,
    api_url: str = HERO_SMS_API_URL,
    provider_name: str = "Hero SMS",
    provider_params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Decimal:
    key = api_key.strip()
    if not key:
        raise ValueError(f"{provider_name} API key is required")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    try:
        response = await client.get(
            api_url,
            params=_request_params(
                {"api_key": key, "action": "getBalance"}, provider_params
            ),
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"{provider_name} returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError(f"Unable to reach {provider_name}") from exc
    finally:
        if owns_client:
            await client.aclose()

    payload = response.text.strip()
    prefix = "ACCESS_BALANCE:"
    if payload.startswith(prefix):
        try:
            return Decimal(payload[len(prefix):].strip())
        except InvalidOperation as exc:
            raise HeroSmsApiError(f"{provider_name} returned an invalid balance") from exc

    raise _provider_error(payload, "balance", provider_name=provider_name)


async def fetch_operators(
    api_key: str,
    country_id: int,
    *,
    api_url: str = HERO_SMS_API_URL,
    provider_name: str = "Hero SMS",
    provider_params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    key = api_key.strip()
    if not key:
        raise ValueError(f"{provider_name} API key is required")
    if country_id < 0:
        raise ValueError(f"A valid {provider_name} country is required")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    try:
        response = await client.get(
            api_url,
            params=_request_params(
                {
                    "api_key": key,
                    "action": "getOperators",
                    "country": country_id,
                },
                provider_params,
            ),
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"{provider_name} returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError(f"Unable to reach {provider_name}") from exc
    finally:
        if owns_client:
            await client.aclose()

    raw_payload = response.text.strip()
    try:
        payload = response.json()
    except ValueError as exc:
        if raw_payload in {"BAD_KEY", "NO_KEY", "BAD_ACTION", "ERROR_SQL"}:
            raise _provider_error(
                raw_payload, "operators", provider_name=provider_name
            ) from exc
        raise HeroSmsApiError(f"{provider_name} returned invalid operators JSON") from exc

    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise HeroSmsApiError(f"{provider_name} returned an unexpected operators response")

    country_operators = payload.get("countryOperators")
    if isinstance(country_operators, dict):
        values = country_operators.get(str(country_id), [])
    elif isinstance(country_operators, list):
        values = country_operators
    else:
        raise HeroSmsApiError(f"{provider_name} returned an unexpected operators response")

    if not isinstance(values, list):
        raise HeroSmsApiError(f"{provider_name} returned an unexpected operators response")

    operators: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        operator = value.strip()
        normalized = operator.casefold()
        if not operator or normalized in seen:
            continue
        seen.add(normalized)
        operators.append(operator)
    return operators


async def fetch_telegram_price(
    api_key: str,
    country_id: int,
    *,
    api_url: str = HERO_SMS_API_URL,
    provider_name: str = "Hero SMS",
    provider_params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[Decimal | None, int]:
    key = api_key.strip()
    if not key:
        raise ValueError(f"{provider_name} API key is required")
    if country_id < 0:
        raise ValueError(f"A valid {provider_name} country is required")
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    try:
        response = await client.get(
            api_url,
            params=_request_params(
                {
                    "api_key": key,
                    "action": "getPrices",
                    "service": "tg",
                    "country": country_id,
                },
                provider_params,
            ),
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"{provider_name} returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError(f"Unable to reach {provider_name}") from exc
    finally:
        if owns_client:
            await client.aclose()

    raw_payload = response.text.strip()
    try:
        payload = response.json()
    except ValueError as exc:
        if raw_payload in {
            "BAD_KEY", "NO_KEY", "BAD_ACTION", "ERROR_SQL",
            "BAD_OPERATOR", "WRONG_OPERATOR", "BAD_SERVICE", "WRONG_SERVICE",
        }:
            raise _provider_error(
                raw_payload, "Telegram price", provider_name=provider_name
            ) from exc
        raise HeroSmsApiError(f"{provider_name} returned invalid prices JSON") from exc

    if not isinstance(payload, dict):
        raise HeroSmsApiError(f"{provider_name} returned an unexpected prices response")

    country_prices = payload.get(str(country_id))
    if country_prices is None:
        return None, 0
    if not isinstance(country_prices, dict):
        raise HeroSmsApiError(f"{provider_name} returned an unexpected prices response")

    telegram = country_prices.get("tg")
    if telegram is None:
        return None, 0
    if not isinstance(telegram, dict) or "cost" not in telegram:
        raise HeroSmsApiError(f"{provider_name} returned an unexpected Telegram price")

    try:
        price = Decimal(str(telegram["cost"]))
        count = int(telegram.get("count", 0))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HeroSmsApiError(f"{provider_name} returned an invalid Telegram price") from exc
    if price < 0 or count < 0:
        raise HeroSmsApiError(f"{provider_name} returned an invalid Telegram price")
    return price, count


async def fetch_telegram_offers(
    api_key: str,
    country_id: int,
    *,
    service: str = "tg",
    api_url: str = HERO_SMS_OFFERS_URL,
    provider_name: str = "Hero SMS",
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Return Telegram activation offers for a country from the REST offers API.

    Response shape:
      {
        "price": Decimal | None,          # recommended max price
        "available": int,                 # total numbers (or recommended tier count)
        "offers": [{"price": Decimal, "available": int}, ...],
      }
    """
    key = api_key.strip()
    service_code = service.strip()
    if not key:
        raise ValueError(f"{provider_name} API key is required")
    if country_id < 0:
        raise ValueError(f"A valid {provider_name} country is required")
    if not service_code:
        raise ValueError(f"A valid {provider_name} service is required")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    try:
        response = await client.get(
            api_url,
            params={
                "services": service_code,
                "countries": str(country_id),
            },
            headers={
                "Accept": "application/json",
                "Authorization": f"ApiKey {key}",
            },
        )
    except httpx.RequestError as exc:
        raise HeroSmsApiError(f"Unable to reach {provider_name}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code == 401:
        raise HeroSmsApiError(f"{provider_name} rejected the API key")
    if response.status_code == 429:
        raise HeroSmsApiError(f"{provider_name} rate limit exceeded")
    if response.status_code >= 400:
        raise HeroSmsApiError(
            f"{provider_name} returned HTTP {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HeroSmsApiError(f"{provider_name} returned invalid offers JSON") from exc

    if not isinstance(payload, dict):
        raise HeroSmsApiError(f"{provider_name} returned an unexpected offers response")

    data = payload.get("data")
    if not isinstance(data, dict):
        return {"price": None, "available": 0, "offers": []}

    service_offers = data.get(service_code)
    if service_offers is None:
        return {"price": None, "available": 0, "offers": []}
    if not isinstance(service_offers, dict):
        raise HeroSmsApiError(f"{provider_name} returned an unexpected offers response")

    country_offer = service_offers.get(str(country_id))
    if country_offer is None:
        return {"price": None, "available": 0, "offers": []}
    if not isinstance(country_offer, dict):
        raise HeroSmsApiError(f"{provider_name} returned an unexpected offers response")

    offers: list[dict[str, Any]] = []
    price_map = country_offer.get("map")
    if isinstance(price_map, dict):
        for raw_price, raw_count in price_map.items():
            try:
                offer_price = Decimal(str(raw_price))
                offer_count = int(raw_count)
            except (InvalidOperation, TypeError, ValueError):
                continue
            if offer_price < 0 or offer_count < 0:
                continue
            offers.append({"price": offer_price, "available": offer_count})
        offers.sort(key=lambda item: item["price"])

    total_available = 0
    counts = country_offer.get("counts")
    if isinstance(counts, dict) and "total" in counts:
        try:
            total_available = max(0, int(counts["total"]))
        except (TypeError, ValueError):
            total_available = 0
    if total_available <= 0 and offers:
        total_available = max(int(item["available"]) for item in offers)

    recommended: Decimal | None = None
    prices = country_offer.get("prices")
    if isinstance(prices, dict):
        for key_name in ("retail", "min", "default"):
            if key_name not in prices:
                continue
            try:
                candidate = Decimal(str(prices[key_name]))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if candidate >= 0:
                recommended = candidate
                break

    # Prefer the cheapest mapped tier that still has stock. When the catalog
    # "from" price has no inventory (defaultPrice == 0), this surfaces the
    # first actually purchaseable maxPrice instead of a stale catalog value.
    if offers:
        stocked = [item for item in offers if item["available"] > 0]
        if stocked:
            recommended = stocked[0]["price"]
            if total_available <= 0:
                total_available = int(stocked[0]["available"])
        elif recommended is None and offers:
            recommended = offers[0]["price"]

    return {
        "price": recommended,
        "available": total_available,
        "offers": offers,
    }


async def fetch_countries(
    api_key: str,
    *,
    api_url: str = HERO_SMS_API_URL,
    provider_name: str = "Hero SMS",
    provider_params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    key = api_key.strip()
    if not key:
        raise ValueError(f"{provider_name} API key is required")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    try:
        response = await client.get(
            api_url,
            params=_request_params(
                {"api_key": key, "action": "getCountries"}, provider_params
            ),
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"{provider_name} returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError(f"Unable to reach {provider_name}") from exc
    finally:
        if owns_client:
            await client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise HeroSmsApiError(f"{provider_name} returned invalid JSON") from exc

    if isinstance(payload, dict):
        values = payload.values()
    elif isinstance(payload, list):
        values = payload
    else:
        raise HeroSmsApiError(f"{provider_name} returned an unexpected countries response")

    countries: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict) or value.get("visible") != 1:
            continue
        try:
            countries.append(
                {
                    "id": int(value["id"]),
                    "rus": str(value.get("rus", "")),
                    "eng": str(value.get("eng", "")),
                    "chn": str(value.get("chn", "")),
                    "visible": 1,
                    "retry": int(value.get("retry", 0)),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    if not countries:
        raise HeroSmsApiError(f"{provider_name} returned no available countries")

    countries.sort(key=lambda country: country["id"])
    return countries


async def request_number_v2(
    api_key: str,
    country_id: int,
    operator: str,
    *,
    max_price: Decimal | None = None,
    api_url: str = HERO_SMS_API_URL,
    provider_name: str = "Hero SMS",
    provider_params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Purchase a Telegram number at a fixed offer price.

    Uses the SMS-Activate-compatible stub with ``maxPrice`` +
    ``fixedPrice=true``.
    Without ``fixedPrice``, ``maxPrice`` is only a Free Price ceiling and can
    fill cheaper numbers (e.g. 0.9765 under a 1.0742 start price).

    The website REST ``POST /api/v1/activations`` path requires a browser
    session and returns 401 for API keys, so it is not used here.
    """
    key = api_key.strip()
    operator_name = operator.strip()
    if not key:
        raise ValueError(f"{provider_name} API key is required")
    if country_id < 0:
        raise ValueError(f"A valid {provider_name} country is required")
    if not operator_name:
        raise ValueError(f"A valid {provider_name} operator is required")
    if max_price is None or max_price <= 0:
        raise ValueError("A positive Telegram purchase price is required")

    params: dict[str, Any] = {
        "api_key": key,
        "action": "getNumberV2",
        "service": "tg",
        "country": country_id,
        "operator": operator_name,
        "maxPrice": str(max_price),
        # Official HeroSMS/SMS-Activate clients send this to lock the bid
        # to maxPrice instead of filling any cheaper Free Price number.
        "fixedPrice": "true",
    }

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
    try:
        response = await client.get(
            api_url,
            params=_request_params(params, provider_params),
        )
    except httpx.RequestError as exc:
        raise HeroSmsApiError(f"Unable to reach {provider_name}") from exc
    finally:
        if owns_client:
            await client.aclose()

    raw_payload = response.text.strip()
    if response.status_code == 404:
        raise _provider_error(
            "NO_NUMBERS", "number purchase", provider_name=provider_name
        )
    if response.status_code >= 400:
        raise HeroSmsApiError(
            f"{provider_name} returned HTTP {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise _provider_error(
            raw_payload, "number purchase", provider_name=provider_name
        ) from exc
    if isinstance(payload, dict) and "activationId" not in payload:
        error_code = str(
            payload.get("error")
            or payload.get("message")
            or payload.get("status")
            or raw_payload
            or "NO_NUMBERS"
        ).strip()
        raise _provider_error(
            error_code, "number purchase", provider_name=provider_name
        )
    if not isinstance(payload, dict):
        raise HeroSmsApiError(f"{provider_name} returned an unexpected number response")

    try:
        activation_id = str(payload["activationId"])
        phone_number = str(payload["phoneNumber"])
        activation_cost = Decimal(str(payload["activationCost"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise HeroSmsApiError(
            f"{provider_name} returned an invalid number response"
        ) from exc
    if not activation_id or not phone_number or activation_cost < 0:
        raise HeroSmsApiError(f"{provider_name} returned an invalid number response")

    return {
        "activation_id": activation_id,
        "phone_number": phone_number,
        "activation_cost": activation_cost,
        "currency": int(payload.get("currency", 840)),
        "operator": str(payload.get("activationOperator", operator_name)),
        "can_get_another_sms": bool(payload.get("canGetAnotherSms", False)),
    }


async def get_activation_status(
    api_key: str,
    activation_id: str,
    *,
    api_url: str = HERO_SMS_API_URL,
    provider_name: str = "Hero SMS",
    provider_params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, str | None]:
    key = api_key.strip()
    activation = activation_id.strip()
    if not key:
        raise ValueError(f"{provider_name} API key is required")
    if not activation:
        raise ValueError(f"{provider_name} activation ID is required")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
    try:
        response = await client.get(
            api_url,
            params=_request_params(
                {"api_key": key, "action": "getStatus", "id": activation},
                provider_params,
            ),
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"{provider_name} returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError(f"Unable to reach {provider_name}") from exc
    finally:
        if owns_client:
            await client.aclose()

    payload = response.text.strip()
    if payload.startswith("STATUS_OK:"):
        return "STATUS_OK", payload.split(":", 1)[1]
    if payload.startswith("STATUS_WAIT_RETRY:"):
        return "STATUS_WAIT_RETRY", None
    if payload in {
        "STATUS_WAIT_CODE", "STATUS_WAIT_RETRY", "STATUS_WAIT_RESEND",
        "STATUS_CANCEL",
    }:
        return payload, None
    raise _provider_error(payload, "activation status", provider_name=provider_name)


async def close_activation(
    api_key: str,
    activation_id: str,
    *,
    cancel: bool,
    api_url: str = HERO_SMS_API_URL,
    provider_name: str = "Hero SMS",
    provider_params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    key = api_key.strip()
    activation = activation_id.strip()
    if not key:
        raise ValueError(f"{provider_name} API key is required")
    if not activation:
        raise ValueError(f"{provider_name} activation ID is required")

    action = "cancelActivation" if cancel else "finishActivation"
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
    try:
        response = await client.get(
            api_url,
            params=_request_params(
                {"api_key": key, "action": action, "id": activation},
                provider_params,
            ),
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"{provider_name} returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError(f"Unable to reach {provider_name}") from exc
    finally:
        if owns_client:
            await client.aclose()
