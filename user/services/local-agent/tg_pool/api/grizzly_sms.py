from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from tg_pool.api.hero_sms import (
    HeroSmsApiError,
    _provider_error,
    fetch_balance as _fetch_balance,
    fetch_countries as _fetch_countries,
    fetch_telegram_price as _fetch_telegram_price,
)


GRIZZLY_SMS_API_URL = "https://api.grizzlysms.com/stubs/handler_api.php"
GRIZZLY_SMS_PROVIDER_NAME = "GrizzlySMS"


async def fetch_balance(
    api_key: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> Decimal:
    return await _fetch_balance(
        api_key,
        api_url=GRIZZLY_SMS_API_URL,
        provider_name=GRIZZLY_SMS_PROVIDER_NAME,
        client=client,
    )


async def fetch_countries(
    api_key: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    # GrizzlySMS declares sms-activate API compatibility. Its compatible
    # getCountries action supplies names for the numeric country codes used by
    # the documented getPrices/getNumberV2 actions.
    return await _fetch_countries(
        api_key,
        api_url=GRIZZLY_SMS_API_URL,
        provider_name=GRIZZLY_SMS_PROVIDER_NAME,
        client=client,
    )


async def fetch_operators(
    api_key: str,
    country_id: int,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    del client
    if not api_key.strip():
        raise ValueError("GrizzlySMS API key is required")
    if country_id < 0:
        raise ValueError("A valid GrizzlySMS country is required")
    # GrizzlySMS documents providerIds rather than a mobile-operator lookup.
    # Returning no named operators lets the shared UI select its neutral "any".
    return []


async def fetch_telegram_price(
    api_key: str,
    country_id: int,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[Decimal | None, int]:
    return await _fetch_telegram_price(
        api_key,
        country_id,
        api_url=GRIZZLY_SMS_API_URL,
        provider_name=GRIZZLY_SMS_PROVIDER_NAME,
        client=client,
    )


async def request_number_v2(
    api_key: str,
    country_id: int,
    operator: str,
    *,
    max_price: Decimal | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    key = api_key.strip()
    if not key:
        raise ValueError("GrizzlySMS API key is required")
    if country_id < 0:
        raise ValueError("A valid GrizzlySMS country is required")
    if not operator.strip():
        raise ValueError("A valid GrizzlySMS provider selection is required")

    params: dict[str, Any] = {
        "api_key": key,
        "action": "getNumberV2",
        "service": "tg",
        "country": country_id,
    }
    if max_price is not None:
        if max_price <= 0:
            raise ValueError("Maximum price must be greater than zero")
        params["maxPrice"] = str(max_price)

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
    try:
        response = await client.get(GRIZZLY_SMS_API_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"GrizzlySMS returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError("Unable to reach GrizzlySMS") from exc
    finally:
        if owns_client:
            await client.aclose()

    raw_payload = response.text.strip()
    try:
        payload = response.json()
    except ValueError as exc:
        raise _provider_error(
            raw_payload,
            "number purchase",
            provider_name=GRIZZLY_SMS_PROVIDER_NAME,
        ) from exc
    if not isinstance(payload, dict):
        raise HeroSmsApiError("GrizzlySMS returned an unexpected number response")

    try:
        activation_id = str(payload["activationId"])
        phone_number = str(payload["phoneNumber"])
        activation_cost = Decimal(str(payload["activationCost"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise HeroSmsApiError("GrizzlySMS returned an invalid number response") from exc
    if not activation_id or not phone_number or activation_cost < 0:
        raise HeroSmsApiError("GrizzlySMS returned an invalid number response")

    return {
        "activation_id": activation_id,
        "phone_number": phone_number,
        "activation_cost": activation_cost,
        "currency": int(payload.get("currency", 840)),
        "operator": operator.strip(),
        "can_get_another_sms": str(payload.get("canGetAnotherSms", "0")) == "1",
    }


async def close_activation(
    api_key: str,
    activation_id: str,
    *,
    cancel: bool,
    client: httpx.AsyncClient | None = None,
) -> None:
    key = api_key.strip()
    activation = activation_id.strip()
    if not key:
        raise ValueError("GrizzlySMS API key is required")
    if not activation:
        raise ValueError("GrizzlySMS activation ID is required")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
    try:
        response = await client.get(
            GRIZZLY_SMS_API_URL,
            params={
                "api_key": key,
                "action": "setStatus",
                "status": "8" if cancel else "6",
                "id": activation,
            },
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"GrizzlySMS returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError("Unable to reach GrizzlySMS") from exc
    finally:
        if owns_client:
            await client.aclose()

    payload = response.text.strip()
    expected = "ACCESS_CANCEL" if cancel else "ACCESS_ACTIVATION"
    if payload != expected:
        raise _provider_error(
            payload,
            "activation update",
            provider_name=GRIZZLY_SMS_PROVIDER_NAME,
        )
