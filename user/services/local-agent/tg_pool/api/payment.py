from __future__ import annotations

import os
from typing import Any, Optional

import httpx


class PaymentApiError(RuntimeError):
    """Raised when the central payment authority cannot complete an operation."""


def _server_url() -> str:
    value = os.getenv("PAYMENT_SERVER_URL", "").strip().rstrip("/")
    if not value:
        raise PaymentApiError("PAYMENT_SERVER_URL is not configured")
    return value


def _headers(api_key: str) -> dict[str, str]:
    key = api_key.strip()
    if not key:
        raise ValueError("Payment API key is required")
    return {"Authorization": f"Bearer {key}"}


def _error_message(response: httpx.Response, operation: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        if detail is not None:
            return str(detail)
    return f"Payment service {operation} failed with HTTP {response.status_code}"


async def _request(
    method: str,
    path: str,
    api_key: str,
    *,
    json_body: Optional[dict[str, Any]] = None,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(base_url=_server_url(), timeout=timeout)
    try:
        try:
            response = await client.request(
                method,
                path,
                headers=_headers(api_key),
                json=json_body,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise PaymentApiError(f"Payment service timed out during {path}") from exc
        except httpx.HTTPError as exc:
            raise PaymentApiError("Unable to reach the payment service") from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise PaymentApiError(_error_message(response, path))
        try:
            payload = response.json()
        except ValueError as exc:
            raise PaymentApiError("Payment service returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise PaymentApiError("Payment service returned an unexpected response")
        return payload
    finally:
        if owns_client:
            await client.aclose()


async def fetch_me(
    api_key: str, *, client: Optional[httpx.AsyncClient] = None
) -> dict[str, Any]:
    return await _request("GET", "/v1/me", api_key, client=client)


async def fetch_balance(
    api_key: str, *, client: Optional[httpx.AsyncClient] = None
) -> dict[str, Any]:
    return await _request("GET", "/v1/balance", api_key, client=client)


async def fetch_catalog(
    api_key: str, *, client: Optional[httpx.AsyncClient] = None
) -> list[dict[str, Any]]:
    payload = await _request("GET", "/v1/products", api_key, client=client)
    items = payload.get("items")
    if not isinstance(items, list):
        raise PaymentApiError("Payment service returned an invalid product catalog")
    return [item for item in items if isinstance(item, dict)]


async def create_order(
    api_key: str,
    *,
    product_id: int,
    quantity: int,
    external_order_id: str,
    client: Optional[httpx.AsyncClient] = None,
) -> dict[str, Any]:
    return await _request(
        "POST",
        "/v1/orders",
        api_key,
        json_body={
            "product_id": product_id,
            "quantity": quantity,
            "external_order_id": external_order_id,
        },
        client=client,
        timeout=180.0,
    )
