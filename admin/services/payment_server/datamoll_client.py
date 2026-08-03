from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable, Mapping
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import quote

import httpx


DATAMOLL_API_URL = "https://datamollcore.com/api/v1/provider"
DATAMOLL_PROVIDER_NAME = "Datamoll"
DATAMOLL_USER_AGENT = "tg-pool-framework/1.0"
class DatamollApiError(RuntimeError):
    """Raised when Datamoll cannot complete a provider API operation."""


def _headers(api_key: str, api_secret: str) -> dict[str, str]:
    key = api_key.strip()
    secret = api_secret.strip()
    if not key or not secret:
        raise ValueError("Datamoll API key and API secret are required")
    return {
        "X-Provider-Key": f"{key}:{secret}",
        "User-Agent": DATAMOLL_USER_AGENT,
        "Accept": "application/json",
    }


def _error_message(response: httpx.Response, operation: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            if message:
                return message
    return f"Datamoll {operation} failed with HTTP {response.status_code}"


async def _send(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    api_key: str,
    api_secret: str,
    operation: str,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
    extra_headers: Optional[dict[str, str]] = None,
    propagate_timeout: bool = False,
) -> httpx.Response:
    headers = _headers(api_key, api_secret)
    if extra_headers:
        headers.update(extra_headers)
    try:
        return await client.request(
            method,
            f"{DATAMOLL_API_URL}{path}",
            headers=headers,
            params=params,
            json=json_body,
        )
    except httpx.TimeoutException as exc:
        if propagate_timeout:
            raise
        raise DatamollApiError(
            f"Datamoll timed out during {operation}"
        ) from exc
    except httpx.HTTPError as exc:
        raise DatamollApiError(f"Unable to reach Datamoll for {operation}") from exc


def _json_object(response: httpx.Response, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise DatamollApiError(
            f"Datamoll returned invalid JSON for {operation}"
        ) from exc
    if not isinstance(payload, dict):
        raise DatamollApiError(
            f"Datamoll returned an unexpected {operation} response"
        )
    return payload


async def fetch_balance(
    api_key: str,
    api_secret: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> dict[str, Any]:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=20.0)
    try:
        response = await _send(
            client,
            "GET",
            "/balance",
            api_key=api_key,
            api_secret=api_secret,
            operation="balance request",
        )
        if response.status_code != 200:
            raise DatamollApiError(_error_message(response, "balance request"))
        payload = _json_object(response, "balance")
        return {
            "balance": str(payload.get("balance", "0")),
            "credit_limit": str(payload.get("credit_limit", "0")),
            "available_balance": str(payload.get("available_balance", "0")),
            "currency": str(payload.get("currency", "USD")),
        }
    finally:
        if owns_client:
            await client.aclose()


def _catalog_text_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _catalog_text_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _catalog_text_values(nested)


def _is_telegram_product(product: dict[str, Any]) -> bool:
    searchable = " ".join(_catalog_text_values(product)).casefold()
    tokens = (
        "telegram",
        "telegram account",
        "tg account",
        "tg-account",
        "tdata",
        "telethon",
        ".session",
    )
    return any(token in searchable for token in tokens)


def _pagination_object(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("pagination", "page", "meta"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _has_more_catalog_pages(payload: dict[str, Any]) -> bool:
    pagination = _pagination_object(payload)
    for source in (payload, pagination):
        for key in ("has_more", "has_next_page", "has_next"):
            value = source.get(key)
            if isinstance(value, bool):
                return value
    return _next_catalog_cursor(payload) is not None


def _next_catalog_cursor(payload: dict[str, Any]) -> Optional[str]:
    pagination = _pagination_object(payload)
    for source in (payload, pagination):
        for key in (
            "next_after_id",
            "after_id",
            "next_cursor",
            "end_cursor",
            "next",
        ):
            value = source.get(key)
            if value is None:
                continue
            cursor = str(value).strip()
            if cursor:
                return cursor
    return None


def _fallback_after_id(items: list[Any]) -> Optional[str]:
    product_ids: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            product_ids.append(int(item.get("product_id") or 0))
        except (TypeError, ValueError):
            continue
    return str(max(product_ids)) if product_ids else None


async def fetch_telegram_catalog(
    api_key: str,
    api_secret: str,
    *,
    language: str = "en",
    client: Optional[httpx.AsyncClient] = None,
) -> list[dict[str, Any]]:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=25.0)
    products: list[dict[str, Any]] = []
    after_id: Optional[str] = None
    try:
        while True:
            params: dict[str, Any] = {
                "limit": 500,
                "only_in_stock": "true",
                "language": language,
            }
            if after_id is not None:
                params["after_id"] = after_id
            response = await _send(
                client,
                "GET",
                "/catalog",
                api_key=api_key,
                api_secret=api_secret,
                operation="catalog request",
                params=params,
            )
            if response.status_code != 200:
                raise DatamollApiError(_error_message(response, "catalog request"))
            payload = _json_object(response, "catalog")
            items = payload.get("items")
            if not isinstance(items, list):
                raise DatamollApiError(
                    "Datamoll returned an unexpected catalog response"
                )
            products.extend(
                item
                for item in items
                if isinstance(item, dict) and _is_telegram_product(item)
            )
            if not _has_more_catalog_pages(payload):
                break
            next_after_id = _next_catalog_cursor(payload) or _fallback_after_id(items)
            if next_after_id is None or next_after_id == after_id:
                raise DatamollApiError("Datamoll catalog pagination is invalid")
            after_id = next_after_id
        return products
    finally:
        if owns_client:
            await client.aclose()


async def _recover_order(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    api_secret: str,
    external_order_id: str,
    attempts: int,
    delay_sec: float,
    sleep_func: Callable[[float], Awaitable[None]],
) -> dict[str, Any]:
    encoded_id = quote(external_order_id, safe="")
    last_message = "Datamoll is still processing the order"
    for attempt in range(attempts):
        if attempt:
            await sleep_func(delay_sec)
        try:
            response = await _send(
                client,
                "GET",
                f"/orders/by-external-id/{encoded_id}",
                api_key=api_key,
                api_secret=api_secret,
                operation="order recovery",
            )
        except DatamollApiError as exc:
            last_message = str(exc)
            if attempt + 1 < attempts:
                continue
            raise
        if response.status_code == 200:
            return _json_object(response, "order")
        if response.status_code in (202, 404):
            last_message = _error_message(response, "order recovery")
            continue
        raise DatamollApiError(_error_message(response, "order recovery"))
    raise DatamollApiError(last_message)


async def create_order_with_recovery(
    api_key: str,
    api_secret: str,
    *,
    product_id: int,
    quantity: int,
    external_order_id: str,
    client: Optional[httpx.AsyncClient] = None,
    recovery_attempts: int = 12,
    recovery_delay_sec: float = 2.0,
    sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any]:
    if product_id < 1:
        raise ValueError("A valid Datamoll product is required")
    if quantity < 1:
        raise ValueError("Datamoll order quantity must be at least 1")
    stable_order_id = external_order_id.strip()
    if not stable_order_id:
        raise ValueError("Datamoll external order ID is required")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)
    try:
        try:
            response = await _send(
                client,
                "POST",
                "/orders",
                api_key=api_key,
                api_secret=api_secret,
                operation="order creation",
                json_body={
                    "product_id": product_id,
                    "quantity": quantity,
                    "external_order_id": stable_order_id,
                },
                extra_headers={"Idempotency-Key": stable_order_id},
                propagate_timeout=True,
            )
        except httpx.TimeoutException:
            return await _recover_order(
                client,
                api_key=api_key,
                api_secret=api_secret,
                external_order_id=stable_order_id,
                attempts=recovery_attempts,
                delay_sec=recovery_delay_sec,
                sleep_func=sleep_func,
            )

        if response.status_code in (200, 201):
            return _json_object(response, "order")
        if response.status_code == 202:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(10.0, max(0.0, float(retry_after or recovery_delay_sec)))
            except ValueError:
                delay = recovery_delay_sec
            if delay:
                await sleep_func(delay)
            return await _recover_order(
                client,
                api_key=api_key,
                api_secret=api_secret,
                external_order_id=stable_order_id,
                attempts=recovery_attempts,
                delay_sec=delay,
                sleep_func=sleep_func,
            )
        raise DatamollApiError(_error_message(response, "order creation"))
    finally:
        if owns_client:
            await client.aclose()
