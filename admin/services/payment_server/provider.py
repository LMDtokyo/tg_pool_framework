from __future__ import annotations

import os
from typing import Any

from payment_server.datamoll_client import create_order_with_recovery, fetch_telegram_catalog


class DatamollProvider:
    def _credentials(self) -> tuple[str, str]:
        api_key = os.getenv("DATAMOLL_PROVIDER_KEY", "").strip()
        api_secret = os.getenv("DATAMOLL_PROVIDER_SECRET", "").strip()
        if not api_key or not api_secret:
            raise RuntimeError(
                "DATAMOLL_PROVIDER_KEY and DATAMOLL_PROVIDER_SECRET must be configured"
            )
        return api_key, api_secret

    async def catalog(self) -> list[dict[str, Any]]:
        api_key, api_secret = self._credentials()
        return await fetch_telegram_catalog(api_key, api_secret)

    async def create_order(
        self, *, product_id: int, quantity: int, external_order_id: str
    ) -> dict[str, Any]:
        api_key, api_secret = self._credentials()
        return await create_order_with_recovery(
            api_key,
            api_secret,
            product_id=product_id,
            quantity=quantity,
            external_order_id=external_order_id,
        )
