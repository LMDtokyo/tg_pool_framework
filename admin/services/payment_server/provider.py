from __future__ import annotations

import os
from typing import Any, Iterable, Mapping, Optional

import httpx
from datamoll_provider import (
    CreateOrderWithRecoveryOptions,
    DatamollProviderClient,
)

_TELEGRAM_TOKENS = (
    "telegram",
    "telegram account",
    "tg account",
    "tg-account",
    "tdata",
    "telethon",
    ".session",
)


def _catalog_text_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _catalog_text_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _catalog_text_values(nested)


def _is_telegram_product(product: Mapping[str, Any]) -> bool:
    searchable = " ".join(_catalog_text_values(product)).casefold()
    return any(token in searchable for token in _TELEGRAM_TOKENS)


class DatamollProvider:
    """Thin wrapper around the official datamoll-provider-sdk client, keeping
    the same catalog()/create_order() surface app.py already depends on."""

    def _credentials(self) -> tuple[str, str]:
        api_key = os.getenv("DATAMOLL_PROVIDER_KEY", "").strip()
        api_secret = os.getenv("DATAMOLL_PROVIDER_SECRET", "").strip()
        if not api_key or not api_secret:
            raise RuntimeError(
                "DATAMOLL_PROVIDER_KEY and DATAMOLL_PROVIDER_SECRET must be configured"
            )
        return api_key, api_secret

    def _client(self, http_client: Optional[httpx.AsyncClient] = None) -> DatamollProviderClient:
        api_key, api_secret = self._credentials()
        return DatamollProviderClient(
            api_key=api_key,
            api_secret=api_secret,
            default_language="en",
            http_client=http_client,
        )

    async def catalog(self, *, http_client: Optional[httpx.AsyncClient] = None) -> list[dict[str, Any]]:
        products: list[dict[str, Any]] = []
        async with self._client(http_client) as client:
            after_id: Optional[int] = None
            while True:
                params: dict[str, Any] = {
                    "limit": 500,
                    "only_in_stock": True,
                    "language": "en",
                }
                if after_id is not None:
                    params["after_id"] = after_id
                page = (await client.list_catalog(params)).data
                products.extend(item for item in page["items"] if _is_telegram_product(item))
                if not page["has_more"] or page["next_after_id"] is None:
                    break
                after_id = page["next_after_id"]
        return products

    async def create_order(
        self,
        *,
        product_id: int,
        quantity: int,
        external_order_id: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> dict[str, Any]:
        async with self._client(http_client) as client:
            order = await client.create_order_with_recovery(
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "external_order_id": external_order_id,
                },
                CreateOrderWithRecoveryOptions(idempotency_key=external_order_id),
            )
        return dict(order.data)
