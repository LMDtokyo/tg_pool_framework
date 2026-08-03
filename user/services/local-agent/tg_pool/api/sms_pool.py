from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from tg_pool.api.hero_sms import (
    HeroSmsApiError,
    fetch_balance as _fetch_balance,
)


SMSPOOL_API_URL = "https://api.smspool.net/stubs/handler_api"
SMSPOOL_SUCCESS_RATE_URL = "https://api.smspool.net/request/success_rate"
SMSPOOL_PURCHASE_URL = "https://api.smspool.net/purchase/sms"
SMSPOOL_CHECK_URL = "https://api.smspool.net/sms/check"
SMSPOOL_CANCEL_URL = "https://api.smspool.net/sms/cancel"
SMSPOOL_PROVIDER_NAME = "SMSpool"
SMSPOOL_TELEGRAM_SERVICE = "Telegram"
SMSPOOL_STUB_PARAMS = {"setting": "smspool", "service": SMSPOOL_TELEGRAM_SERVICE}


def _api_error(payload: Any, operation: str) -> HeroSmsApiError:
    if isinstance(payload, dict):
        error_type = str(payload.get("type", "")).strip()
        type_messages = {
            "OUT_OF_STOCK": "SMSpool has no matching numbers available",
            "BALANCE_ERROR": "SMSpool balance is insufficient",
            "PRICE_NOT_FOUND": "SMSpool price now exceeds the displayed maximum",
        }
        if error_type in type_messages:
            return HeroSmsApiError(type_messages[error_type])
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                message = str(first.get("message", "")).strip()
                if message:
                    return HeroSmsApiError(f"SMSpool {operation} failed: {message}")
        message = str(payload.get("message", "")).strip()
        if message:
            return HeroSmsApiError(f"SMSpool {operation} failed: {message}")
    return HeroSmsApiError(f"SMSpool returned an unexpected {operation} response")


def _normalize_phone_number(payload: dict[str, Any]) -> str:
    number = str(payload.get("number", "")).strip()
    if number:
        return number
    country_code = str(payload.get("cc", "")).strip()
    phone_number = str(payload.get("phonenumber", "")).strip()
    if country_code and phone_number:
        return f"{country_code}{phone_number}"
    return phone_number


async def _fetch_telegram_success_rates(
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    try:
        response = await client.post(
            SMSPOOL_SUCCESS_RATE_URL,
            data={"service": SMSPOOL_TELEGRAM_SERVICE},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"SMSpool returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError("Unable to reach SMSpool") from exc
    finally:
        if owns_client:
            await client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise HeroSmsApiError("SMSpool returned invalid success-rate JSON") from exc

    if isinstance(payload, dict) and payload.get("success") == 0:
        raise _api_error(payload, "success-rate")
    if not isinstance(payload, list):
        raise _api_error(payload, "success-rate")
    return [item for item in payload if isinstance(item, dict)]


async def fetch_balance(
    api_key: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> Decimal:
    return await _fetch_balance(
        api_key,
        api_url=SMSPOOL_API_URL,
        provider_name=SMSPOOL_PROVIDER_NAME,
        client=client,
    )


async def fetch_operators(
    api_key: str,
    country_id: int,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    key = api_key.strip()
    if not key:
        raise ValueError("SMSpool API key is required")
    if country_id < 0:
        raise ValueError("A valid SMSpool country is required")
    return []


async def fetch_telegram_price(
    api_key: str,
    country_id: int,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[Decimal | None, int]:
    key = api_key.strip()
    if not key:
        raise ValueError("SMSpool API key is required")
    if country_id < 0:
        raise ValueError("A valid SMSpool country is required")

    countries = await _fetch_telegram_success_rates(client=client)
    for country in countries:
        try:
            current_id = int(country.get("country_id", country.get("country")))
        except (TypeError, ValueError):
            continue
        if current_id != country_id:
            continue
        try:
            price = Decimal(str(country.get("price", country.get("low_price", "0"))))
            success_rate = int(float(str(country.get("success_rate", "0"))))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise HeroSmsApiError("SMSpool returned an invalid Telegram price") from exc
        if price < 0 or success_rate < 0:
            raise HeroSmsApiError("SMSpool returned an invalid Telegram price")
        return price, success_rate
    return None, 0


async def fetch_countries(
    api_key: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    key = api_key.strip()
    if not key:
        raise ValueError("SMSpool API key is required")

    rows = await _fetch_telegram_success_rates(client=client)
    countries: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        try:
            country_id = int(row.get("country_id", row.get("country")))
        except (TypeError, ValueError):
            continue
        if country_id in seen:
            continue
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        seen.add(country_id)
        countries.append(
            {
                "id": country_id,
                "rus": name,
                "eng": name,
                "chn": name,
                "visible": 1,
                "retry": 0,
            }
        )

    if not countries:
        raise HeroSmsApiError("SMSpool returned no Telegram countries")
    countries.sort(key=lambda country: country["id"])
    return countries


async def request_number(
    api_key: str,
    country_id: int,
    operator: str,
    *,
    max_price: Decimal | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    key = api_key.strip()
    operator_name = operator.strip()
    if not key:
        raise ValueError("SMSpool API key is required")
    if country_id < 0:
        raise ValueError("A valid SMSpool country is required")
    if not operator_name:
        raise ValueError("A valid SMSpool operator is required")

    data: dict[str, Any] = {
        "key": key,
        "country": country_id,
        "service": SMSPOOL_TELEGRAM_SERVICE,
        "activation_type": "SMS",
    }
    if max_price is not None:
        if max_price <= 0:
            raise ValueError("Maximum price must be greater than zero")
        data["max_price"] = str(max_price)
    if operator_name.casefold() != "any":
        data["pool"] = operator_name

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
    try:
        response = await client.post(SMSPOOL_PURCHASE_URL, data=data)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"SMSpool returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError("Unable to reach SMSpool") from exc
    finally:
        if owns_client:
            await client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise HeroSmsApiError("SMSpool returned invalid number JSON") from exc
    if isinstance(payload, dict) and int(payload.get("success", 0) or 0) == 1:
        activation_id = str(payload.get("order_id", "")).strip()
        phone_number = _normalize_phone_number(payload)
        try:
            activation_cost = Decimal(str(payload.get("cost", max_price or "0")))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise HeroSmsApiError("SMSpool returned an invalid number response") from exc
        if not activation_id or not phone_number or activation_cost < 0:
            raise HeroSmsApiError("SMSpool returned an invalid number response")
        return {
            "activation_id": activation_id,
            "phone_number": phone_number,
            "activation_cost": activation_cost,
            "currency": 840,
            "operator": operator_name,
            "can_get_another_sms": False,
        }
    raise _api_error(payload, "number purchase")


async def get_activation_status(
    api_key: str,
    activation_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, str | None]:
    key = api_key.strip()
    activation = activation_id.strip()
    if not key:
        raise ValueError("SMSpool API key is required")
    if not activation:
        raise ValueError("SMSpool activation ID is required")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
    try:
        response = await client.post(
            SMSPOOL_CHECK_URL,
            data={"key": key, "orderid": activation},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"SMSpool returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError("Unable to reach SMSpool") from exc
    finally:
        if owns_client:
            await client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise HeroSmsApiError("SMSpool returned invalid activation status JSON") from exc
    if not isinstance(payload, dict):
        raise _api_error(payload, "activation status")

    try:
        status = int(payload.get("status", 0))
    except (TypeError, ValueError) as exc:
        raise HeroSmsApiError("SMSpool returned an invalid activation status") from exc
    if status == 3:
        code = str(payload.get("sms", "")).strip()
        return "STATUS_OK", code or None
    if status == 1:
        return "STATUS_WAIT_CODE", None
    if status == 6:
        return "STATUS_CANCEL", None
    raise _api_error(payload, "activation status")


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
        raise ValueError("SMSpool API key is required")
    if not activation:
        raise ValueError("SMSpool activation ID is required")

    if not cancel:
        return

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
    try:
        response = await client.post(
            SMSPOOL_CANCEL_URL,
            data={"key": key, "orderid": activation},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HeroSmsApiError(
            f"SMSpool returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HeroSmsApiError("Unable to reach SMSpool") from exc
    finally:
        if owns_client:
            await client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise HeroSmsApiError("SMSpool returned invalid cancellation JSON") from exc
    if isinstance(payload, dict) and int(payload.get("success", 0) or 0) == 1:
        return
    message = ""
    if isinstance(payload, dict):
        message = str(payload.get("message", "")).casefold()
    if "cannot be cancelled yet" in message:
        return
    raise _api_error(payload, "cancellation")
