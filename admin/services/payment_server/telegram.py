from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("payment_server.telegram")


def _trust_env() -> bool:
    return os.getenv("PAYMENT_TELEGRAM_TRUST_ENV", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def telegram_client(*, timeout: float = 20.0) -> httpx.AsyncClient:
    token = os.getenv("PAYMENT_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("PAYMENT_TELEGRAM_BOT_TOKEN is not configured")
    return httpx.AsyncClient(
        base_url=f"https://api.telegram.org/bot{token}",
        timeout=timeout,
        trust_env=_trust_env(),
    )


async def send_telegram_message(
    chat_id: int | str,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    async with telegram_client() as client:
        response = await client.post(
            "/sendMessage",
            json=payload,
        )
        response.raise_for_status()


async def notify_deposit(
    *,
    telegram_user_id: str | None,
    amount: str,
    asset: str,
    transaction_hash: str,
) -> None:
    if not telegram_user_id or not os.getenv("PAYMENT_TELEGRAM_BOT_TOKEN", "").strip():
        return
    try:
        await send_telegram_message(
            telegram_user_id,
            (
                "Deposit confirmed.\n\n"
                f"Amount: {amount} {asset}\n"
                f"Transaction: {transaction_hash}\n\n"
                "Your purchasing balance has been updated."
            ),
        )
    except Exception:
        logger.exception(
            "Unable to send deposit notification for transaction %s",
            transaction_hash,
        )
